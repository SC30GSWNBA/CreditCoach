"""Per-user memory (Task 16): what each user said and did, kept across sessions, machines and teammates.

Three kinds of memory, kept in Neon Postgres (``creditcoach.memory.pg``) when ``DATABASE_URL`` is set, so every
teammate and every deployment reads and writes the same history; otherwise in plain files under
``memory/<user_id>/`` (the "files" backend, used by tests and kept in git as the archive from before the move):

    Episodic    What happened, as it happened: one JSON Lines file per chat session in ``episodes/``, with the
                login, every message and reply, explicit goal changes, and the logout. Written live by the chat UI.
    Semantic    What is true about the user: their goal (target score, target date, purpose) and facts they've
                told us ("saving for a car", "getting married next year").
    Procedural  How the user likes to be helped: preferences such as "keep answers short" or "amounts in lakh".

The goal is the one semantic record with its own write path. It changes only through an explicit ``goal_set``
event (``set_goal``), never through consolidation, so a stated goal is never silently overridden
(requirements.md §6). Everything else semantic and procedural, plus a summary of each session, is produced by
"dreaming" (``creditcoach.memory.dream``): a between-session step that reads new episodes and rewrites the user's
consolidated memory into a new file in ``dreams/``.

Both backends are append-only: an event or a dream is never edited after it's written (files: a new session is a
new episode file and a new dream a new dream file, each with a unique name; Postgres: a trigger refuses UPDATE and
DELETE). Reading merges everything: episodes are replayed in time order, and the newest dream is the consolidated
memory. ``config.MEMORY_BACKEND`` is read at call time, so tests can force "files".

Schema (version 1) is documented in ``docs/memory.md``.

Example:
    >>> from creditcoach.memory import store
    >>> s = store.start_session("USR-001", source="cli")
    >>> store.set_goal(s, {"target_score": 720, "target_date": "2027-09", "purpose": "buy a car"}, quote="...")
    >>> store.load("USR-001").goal
    Goal(target_score=720, target_date='2027-09', purpose='buy a car', ...)
"""

import json
import re
import secrets
import subprocess
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from creditcoach import config

VERSION = 1
USER_ID = re.compile(r"USR-\d{3}")
EVENT_TYPES = {"login", "user_message", "assistant_message", "error", "goal_set", "goal_cleared", "logout",
               "session_end"}
SOURCES = {"chat_ui", "cli", "eval", "evidence"}
_LOCK = threading.RLock()  # appends from Gradio's worker threads; now() takes it too


class MemoryRecordError(ValueError):
    """Raised for an invalid memory record (bad user id, unknown event type, out-of-range goal)."""


# ---- Records ----

@dataclass(frozen=True)
class Goal:
    """A user's credit goal: the semantic record Task 16 specifies.

    Attributes:
        target_score: The score the user wants, 300-900 (Indian bureau range), or None if not stated.
        target_date: When they want it, as ``YYYY-MM``, or ``YYYY`` when the user named only a year ("by next
            year" said in 2026 is ``2027``), or None if not stated.
        purpose: Why, in the user's words ("buy a car"), or None if not stated.
        set_at: When the goal was stated (UTC, ISO 8601).
        session: The episode it was stated in.
        quote: The user's own words that set it, kept so the goal can always be traced to what they said.
    """
    target_score: int | None
    target_date: str | None
    purpose: str | None
    set_at: str
    session: str
    quote: str


@dataclass
class Event:
    """One line of an episode file."""
    v: int
    ts: str
    user_id: str
    session: str
    type: str
    text: str = ""
    meta: dict = field(default_factory=dict)


@dataclass
class Episode:
    """One chat session: its events in order. ``path`` is its file, or None in the Postgres backend."""
    session: str
    path: Path | None
    events: list[Event]

    @property
    def started(self) -> str:
        return self.events[0].ts if self.events else ""

    @property
    def ended(self) -> str:
        return self.events[-1].ts if self.events else ""

    def turns(self) -> list[tuple[str, str]]:
        """(role, text) for every message and reply, in order."""
        roles = {"user_message": "user", "assistant_message": "assistant"}
        return [(roles[e.type], e.text) for e in self.events if e.type in roles]


@dataclass
class UserMemory:
    """Everything remembered about one user, merged from all episode and dream files.

    Attributes:
        user_id: The user.
        episodes: Every session, oldest first.
        goal: The current goal (last ``goal_set``, unless a later ``goal_cleared``), or None.
        goal_history: Every goal the user has set, oldest first, so a change can be shown as old -> new.
        dream: The newest consolidated memory (``dreams/*.json``), or None if none has run yet.
    """
    user_id: str
    episodes: list[Episode]
    goal: Goal | None
    goal_history: list[Goal]
    dream: dict | None

    def unconsolidated(self, exclude: str | None = None) -> list[Episode]:
        """Episodes the newest dream hasn't read yet (optionally leaving out a session still in progress)."""
        covered = set((self.dream or {}).get("covers", []))
        return [e for e in self.episodes if e.session not in covered and e.session != exclude and e.turns()]


# ---- Backend ----

def _db():
    """The Postgres module when ``config.MEMORY_BACKEND`` is "postgres", else None (files)."""
    if config.MEMORY_BACKEND == "postgres":
        from creditcoach.memory import pg
        return pg
    if config.MEMORY_BACKEND != "files":
        raise MemoryRecordError(f"unknown memory backend {config.MEMORY_BACKEND!r} (use 'postgres' or 'files')")
    return None


# ---- Validation ----

def check_user(user_id: str) -> str:
    """Return ``user_id`` if it has the dataset's form (``USR-NNN``), else raise ``MemoryRecordError``."""
    if not isinstance(user_id, str) or not USER_ID.fullmatch(user_id):
        raise MemoryRecordError(f"invalid user id {user_id!r}")
    return user_id


def check_goal(goal: dict) -> dict:
    """Validate a goal dict and return it normalized.

    Rules: ``target_score`` is an int from 300 to 900; ``target_date`` is ``YYYY-MM`` or ``YYYY``; ``purpose`` is a non-empty
    string of at most 200 characters. Each may be None, but not all three.

    Raises:
        MemoryRecordError: If a field is out of range, malformed, or every field is missing.
    """
    unknown = set(goal) - {"target_score", "target_date", "purpose"}
    if unknown:
        raise MemoryRecordError(f"unknown goal fields {sorted(unknown)}")
    score, date, purpose = goal.get("target_score"), goal.get("target_date"), goal.get("purpose")
    if score is not None and (isinstance(score, bool) or not isinstance(score, int) or not 300 <= score <= 900):
        raise MemoryRecordError(f"target_score must be an integer from 300 to 900, got {score!r}")
    if date is not None and not (isinstance(date, str) and re.fullmatch(r"20\d\d(-(0[1-9]|1[0-2]))?", date)):
        raise MemoryRecordError(f"target_date must be YYYY-MM or YYYY, got {date!r}")
    if purpose is not None:
        if not isinstance(purpose, str) or not purpose.strip() or len(purpose) > 200:
            raise MemoryRecordError("purpose must be a non-empty string of at most 200 characters")
        purpose = purpose.strip()
    if score is None and date is None and purpose is None:
        raise MemoryRecordError("a goal needs at least one of target_score, target_date, purpose")
    return {"target_score": score, "target_date": date, "purpose": purpose}


# ---- Paths and time ----

_last = [datetime.min.replace(tzinfo=timezone.utc)]


def now() -> str:
    """Current UTC time, ISO 8601 to the millisecond, e.g. ``2026-10-02T14:03:22.481Z``.

    Strictly increasing within this process (a repeat is moved 1 ms later), so every event one machine writes,
    in any session, reads back in the order it happened, even several in the same millisecond.
    """
    with _LOCK:
        n = datetime.now(timezone.utc)
        t = max(n.replace(microsecond=n.microsecond // 1000 * 1000), _last[0] + timedelta(milliseconds=1))
        _last[0] = t
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def stamp_id(ts: str) -> str:
    """A file-name-safe id from a timestamp, to the second: ``2026-10-02T14:03:22.481Z`` -> ``20261002T140322Z``."""
    return ts[:19].replace("-", "").replace(":", "") + "Z"


def user_dir(user_id: str) -> Path:
    """``memory/<user_id>/`` (read at call time, so tests can point ``config.MEMORY_DIR`` elsewhere)."""
    return Path(config.MEMORY_DIR) / check_user(user_id)


@lru_cache(maxsize=1)
def recorded_by() -> str:
    """Who is running this copy of the app (``git config user.name``), so a pulled episode shows who recorded it."""
    try:
        name = subprocess.run(["git", "config", "user.name"], cwd=config.ROOT, capture_output=True, text=True,
                              timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        name = ""
    return name or "unknown"


# ---- Writing ----

@dataclass
class Session:
    """An open episode: where its events go (``path`` is None in the Postgres backend). Create with ``start_session``."""
    user_id: str
    session: str
    path: Path | None


def start_session(user_id: str, source: str = "chat_ui", meta: dict | None = None) -> Session:
    """Open a new episode for a user and record the ``login`` event.

    Args:
        user_id: The signed-in user.
        source: "chat_ui", "cli", "eval" or "evidence".
        meta: Extra login details to keep (for example the Gradio session hash).

    Returns:
        The ``Session`` to pass to ``record`` and ``set_goal``.
    """
    if source not in SOURCES:
        raise MemoryRecordError(f"unknown source {source!r}")
    stamp = now()
    session = f"{stamp_id(stamp)}-{secrets.token_hex(3)}"  # e.g. 20261002T140322Z-a1b2c3
    path = None if _db() else user_dir(user_id) / "episodes" / f"{session}.jsonl"
    s = Session(user_id, session, path)
    record(s, "login", meta={"source": source, "recorded_by": recorded_by(), **(meta or {})}, ts=stamp)
    return s


def record(s: Session, type_: str, text: str = "", meta: dict | None = None, ts: str | None = None) -> Event:
    """Append one event to an episode.

    Raises:
        MemoryRecordError: For an unknown event type.
    """
    if type_ not in EVENT_TYPES:
        raise MemoryRecordError(f"unknown event type {type_!r}")
    event = Event(v=VERSION, ts=ts or now(), user_id=s.user_id, session=s.session, type=type_, text=text,
                  meta=meta or {})
    if db := _db():
        db.append_event(asdict(event))
        return event
    line = json.dumps(asdict(event), ensure_ascii=False)
    with _LOCK:
        s.path.parent.mkdir(parents=True, exist_ok=True)
        with s.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    return event


def set_goal(s: Session, goal: dict, quote: str) -> Goal:
    """Record an explicit goal change (``goal_set``) and return the new goal.

    The only way a goal changes. ``quote`` is the user's own words that set it; a goal with no quote can't be
    traced to the user, so it is refused.

    Raises:
        MemoryRecordError: If the goal is invalid or the quote is empty.
    """
    goal = check_goal(goal)
    if not quote or not quote.strip():
        raise MemoryRecordError("a goal needs the user's own words (quote) that set it")
    previous = load(s.user_id).goal
    e = record(s, "goal_set", text=quote.strip(),
               meta={"goal": goal, "previous": asdict(previous) if previous else None})
    return Goal(**goal, set_at=e.ts, session=s.session, quote=quote.strip())


def clear_goal(s: Session, quote: str) -> None:
    """Record that the user dropped their goal (``goal_cleared``), in their own words."""
    if not quote or not quote.strip():
        raise MemoryRecordError("clearing a goal needs the user's own words (quote)")
    record(s, "goal_cleared", text=quote.strip())


def save_dream(user_id: str, dream: dict) -> Path | str:
    """Save a consolidated memory as a new dream (never overwriting) and return where: its file, or its row id."""
    check_user(user_id)
    stamp = dream.get("created") or now()
    dream_id = f"{stamp_id(stamp)}-{secrets.token_hex(3)}"
    if db := _db():
        db.save_dream(dream_id, user_id, stamp, dream)
        return dream_id
    path = user_dir(user_id) / "dreams" / f"{dream_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dream, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


# ---- Reading ----

def read_episode(path: Path) -> Episode:
    """Read one episode file. Lines that aren't valid events (for example a half-written last line) are skipped."""
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
            if d.get("type") in EVENT_TYPES:
                events.append(Event(**{k: d[k] for k in ("v", "ts", "user_id", "session", "type")},
                                    text=d.get("text", ""), meta=d.get("meta", {})))
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    return Episode(session=path.stem, path=path, events=events)


def _db_episodes(rows: list[dict]) -> list[Episode]:
    """Group Postgres event rows (already in time order) into episodes."""
    by_session: dict[str, list[Event]] = {}
    for r in rows:
        by_session.setdefault(r["session"], []).append(Event(**r))
    return [Episode(session=k, path=None, events=v) for k, v in by_session.items()]


def load(user_id: str) -> UserMemory:
    """Read everything remembered about a user: every episode, the current goal, and the newest dream.

    Only that user's directory (or rows) is read, and every event is checked to belong to them, so one user's
    memory can never include another's.
    """
    base = user_dir(user_id)
    db = _db()
    if db:
        episodes = _db_episodes(db.events(user_id))
    else:
        episodes = [read_episode(p) for p in (base / "episodes").glob("*.jsonl")]
    episodes.sort(key=lambda e: (e.started, e.session))
    for e in episodes:
        e.events = [ev for ev in e.events if ev.user_id == user_id]
    goal, history = None, []
    ordered = sorted(((ev.ts, i, ev) for e in episodes for i, ev in enumerate(e.events)), key=lambda x: (x[0], x[1]))
    for _, _, ev in ordered:  # time order; within the same millisecond, the order lines were written
        if ev.type == "goal_set":
            try:
                g = check_goal(ev.meta.get("goal", {}))
            except MemoryRecordError:
                continue
            goal = Goal(**g, set_at=ev.ts, session=ev.session, quote=ev.text)
            history.append(goal)
        elif ev.type == "goal_cleared":
            goal = None
    if db:
        dream = db.latest_dream(user_id)
        dream = dream if dream and dream.get("user_id") == user_id else None
        return UserMemory(user_id=user_id, episodes=episodes, goal=goal, goal_history=history, dream=dream)
    dreams = []
    for p in (base / "dreams").glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if d.get("user_id") == user_id:
            dreams.append((d.get("created", ""), p.name, d))
    dream = max(dreams)[2] if dreams else None
    return UserMemory(user_id=user_id, episodes=episodes, goal=goal, goal_history=history, dream=dream)


def users() -> list[str]:
    """User ids that have any memory (a memory directory, or rows in Postgres)."""
    if db := _db():
        return [u for u in db.users() if USER_ID.fullmatch(u)]
    base = Path(config.MEMORY_DIR)
    return sorted(p.name for p in base.glob("USR-*") if p.is_dir() and USER_ID.fullmatch(p.name)) if base.exists() else []


def session_count() -> int:
    """Number of episodes stored, across all users."""
    if db := _db():
        return db.session_count()
    return sum(len(list((user_dir(u) / "episodes").glob("*.jsonl"))) for u in users())
