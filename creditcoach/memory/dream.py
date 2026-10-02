"""Dreaming: between sessions, consolidate a user's new episodes into their long-term memory (Task 16).

The same technique as Anthropic's "dreaming" for Claude Managed Agents, built on CreditCoach's own stack (the
OpenRouter ``SMALL_MODEL``), because the agent runs on GPT-5 through OpenRouter rather than on Managed Agents.
Like sleep consolidating the day, it runs between sessions: it reads the episodes the last dream hasn't seen,
together with the current consolidated memory, and rewrites that memory so it stays accurate and small:

    - adds new facts and preferences the user stated;
    - merges duplicates ("saving for a car" and "wants to buy a car" become one fact);
    - drops what is stale or contradicted, keeping the newer statement;
    - writes a short summary of each new session;
    - lists every change with a reason, so a teammate can audit what was kept, merged or dropped.

The result is a new file in ``memory/<user_id>/dreams/``; earlier dreams and all episodes stay as they were, so
nothing is lost and a bad dream can be redone. The newest dream is the user's consolidated memory.

What dreaming may not do, and how each limit is enforced on the model's output before it is saved:
    Change the goal   The goal changes only through an explicit ``goal_set`` event (``store.set_goal``). Dreaming
                      may only list a *goal candidate*, and only with the user's exact words as its quote; a quote
                      that isn't in one of the user's messages is dropped. The chat asks the user to confirm a candidate
                      before saving it (``memory.recall``).
    Store figures     Scores, balances, limits and ratios go stale and must always come from the tools
                      (system prompt rule 1), so facts and preferences containing ₹ amounts, percentages or a
                      score are dropped.
    Invent sources    Every fact, preference and summary must name sessions it came from; unknown ones are dropped.

Runs automatically when a user signs in to the chat UI (in the background, for their earlier sessions), or by hand:
    uv run python -m creditcoach.memory.dream --user USR-001
    uv run python -m creditcoach.memory.dream --all          # every user with unconsolidated episodes
"""

import argparse
import json
import logging
import re
import threading

from creditcoach import config
from creditcoach.memory import store

log = logging.getLogger(__name__)

MAX_FACTS, MAX_PREFERENCES, MAX_TEXT = 20, 10, 200
ASSISTANT_CHARS = 600  # enough of each reply to know what was discussed; the user's words are kept in full
FIGURE = re.compile(r"₹|\brs\.?\s?\d|\d+(\.\d+)?\s?%|\bscore\b[^.]{0,20}\b[3-9]\d\d\b|\b[3-9]\d\d\b[^.]{0,20}\bscore\b",
                    re.I)
_running: set[str] = set()
_running_lock = threading.Lock()

PROMPT = """You consolidate a credit-coaching assistant's memory of ONE user, between sessions.

You get the user's CURRENT MEMORY (may be empty) and the transcripts of NEW SESSIONS. Return the user's updated
memory as one JSON object with exactly these keys:

{
 "facts": [{"text": "...", "sources": ["<session id>", ...]}],
 "preferences": [{"text": "...", "sources": ["<session id>", ...]}],
 "goal_candidates": [{"target_score": 720 or null, "target_date": "YYYY-MM" or null, "purpose": "..." or null,
                      "quote": "<the user's exact words>", "session": "<session id>"}],
 "session_summaries": [{"session": "<session id>", "summary": "..."}],
 "changes": [{"action": "added|merged|updated|removed", "kind": "fact|preference", "text": "...", "reason": "..."}]
}

Rules:
- facts: durable things the USER said about their own life, plans or situation ("saving for a car", "has an
  education loan they want to prepay", "is getting married in 2027"). Not the assistant's advice. Not credit
  figures: never store a score, balance, limit, ₹ amount or percentage, because those go stale and always come
  live from tools.
- preferences: how the user wants to be helped ("prefers short answers", "wants amounts in lakh", "wants
  step-by-step plans"). Only if the user said or clearly showed it.
- Start from CURRENT MEMORY. Keep what is still true, merge duplicates into one item, and when a new statement
  contradicts an old one keep the newer one. Remove items only when contradicted or clearly stale. Keep at most
  20 facts and 10 preferences, each under 200 characters. Each item's sources lists every session it came from.
- goal_candidates: only when the user explicitly states a credit goal (a target score, a date, a purpose) in the
  NEW SESSIONS. "quote" must be copied exactly, character for character, from one of the user's messages. Do not
  infer a goal from a question like "should I aim for 800?". Dates as YYYY-MM, or YYYY when only a year is
  clear (use the session's date to resolve "next year").
- session_summaries: one per NEW SESSION, one or two sentences on what the user asked and what was covered.
- changes: every fact or preference you added, merged, updated or removed versus CURRENT MEMORY, with a reason.
Return only the JSON object."""


def _transcript(e: store.Episode) -> str:
    """One session as text for the model: the user's words in full, replies shortened."""
    lines = [f"SESSION {e.session} ({e.started} to {e.ended})"]
    for role, text in e.turns():
        lines.append(f"{role.upper()}: {text if role == 'user' else text[:ASSISTANT_CHARS]}")
    lines += [f"[{ev.type}] {ev.text}" for ev in e.events if ev.type in ("goal_set", "goal_cleared")]
    return "\n".join(lines)


def _current(memory: store.UserMemory) -> dict:
    """The parts of the newest dream the model rewrites."""
    d = memory.dream or {}
    return {"facts": d.get("semantic", {}).get("facts", []),
            "preferences": d.get("procedural", {}).get("preferences", [])}


def _call_model(messages: list[dict]) -> tuple[str, str]:
    """Ask SMALL_MODEL for the consolidated memory as JSON. Returns (text, model used)."""
    from creditcoach.llm import _complete

    message, model = _complete(messages, config.SMALL_MODEL, response_format={"type": "json_object"})
    return message.content or "", model


def _parse(text: str) -> dict:
    """The model's JSON object, tolerating a code fence or text around it."""
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else {}


def validate(raw: dict, new: list[store.Episode], memory: store.UserMemory) -> tuple[dict, list[dict]]:
    """Apply dreaming's limits to the model's output.

    Returns:
        ``(clean, rejected)``: the output with every invalid item removed, and each removed item with the reason.
    """
    known = {e.session for e in memory.episodes}
    new_ids = {e.session for e in new}
    user_words = {e.session: [" ".join(t.split()) for r, t in e.turns() if r == "user"] for e in new}
    rejected = []

    def items(entries, kind, limit):
        out = []
        for it in entries if isinstance(entries, list) else []:
            text = str(it.get("text", "")).strip() if isinstance(it, dict) else ""
            sources = [s for s in (it.get("sources") or []) if s in known] if isinstance(it, dict) else []
            reason = ("empty" if not text else "too long" if len(text) > MAX_TEXT else
                      "contains a credit figure (figures come from the tools)" if FIGURE.search(text) else
                      "no known source session" if not sources else None)
            if reason:
                rejected.append({"kind": kind, "item": it, "reason": reason})
            elif text.lower() not in {o["text"].lower() for o in out}:
                out.append({"text": text, "sources": sorted(set(sources))})
        if len(out) > limit:
            rejected.extend({"kind": kind, "item": o, "reason": f"over the limit of {limit}"} for o in out[limit:])
        return out[:limit]

    saved = {" ".join(ev.text.split()) for e in memory.episodes for ev in e.events if ev.type == "goal_set"}
    candidates = []
    for c in raw.get("goal_candidates") or []:
        if not isinstance(c, dict):
            continue
        quote = " ".join(str(c.get("quote", "")).split())
        session = c.get("session")
        try:
            goal = store.check_goal({k: c.get(k) for k in ("target_score", "target_date", "purpose")})
        except store.MemoryRecordError as exc:
            rejected.append({"kind": "goal_candidate", "item": c, "reason": str(exc)})
            continue
        if session not in new_ids or not quote or not any(quote in w for w in user_words.get(session, [])):
            rejected.append({"kind": "goal_candidate", "item": c, "reason": "quote is not the user's exact words"})
            continue
        if any(quote in s or s in quote for s in saved):
            rejected.append({"kind": "goal_candidate", "item": c, "reason": "already saved as a goal_set"})
            continue
        candidates.append({**goal, "quote": quote, "session": session})

    summaries = {s.get("session"): str(s.get("summary", "")).strip()[:400]
                 for s in raw.get("session_summaries") or [] if isinstance(s, dict) and s.get("session") in new_ids}
    clean = {"facts": items(raw.get("facts"), "fact", MAX_FACTS),
             "preferences": items(raw.get("preferences"), "preference", MAX_PREFERENCES),
             "goal_candidates": candidates, "summaries": summaries,
             "changes": [c for c in raw.get("changes") or [] if isinstance(c, dict)][:50]}
    return clean, rejected


def dream(user_id: str, exclude_session: str | None = None, call_model=_call_model) -> dict | None:
    """Consolidate a user's unconsolidated episodes into a new dream file.

    Args:
        user_id: The user.
        exclude_session: A session still in progress, left for the next dream.
        call_model: The model call (replaced in tests).

    Returns:
        The saved dream, or None if there was nothing new to consolidate.
    """
    memory = store.load(user_id)
    new = memory.unconsolidated(exclude=exclude_session)
    if not new:
        return None
    previous = memory.dream or {}
    messages = [{"role": "system", "content": PROMPT},
                {"role": "user", "content": "CURRENT MEMORY:\n" + json.dumps(_current(memory), ensure_ascii=False)
                 + "\n\nNEW SESSIONS:\n\n" + "\n\n".join(_transcript(e) for e in new)}]
    text, model = call_model(messages)
    clean, rejected = validate(_parse(text), new, memory)

    sessions = list(previous.get("episodic", {}).get("sessions", []))
    for e in new:
        sessions.append({"session": e.session, "started": e.started, "ended": e.ended, "turns": len(e.turns()),
                         "logged_out": any(ev.type == "logout" for ev in e.events),
                         "recorded_by": e.events[0].meta.get("recorded_by", "unknown") if e.events else "unknown",
                         "summary": clean["summaries"].get(e.session) or f"{len(e.turns()) // 2} question(s); no summary."})
    old_candidates = previous.get("semantic", {}).get("goal_candidates", [])
    result = {
        "v": store.VERSION, "user_id": user_id, "created": store.now(), "model": model,
        "recorded_by": store.recorded_by(),
        "covers": sorted(set(previous.get("covers", [])) | {e.session for e in new}),
        "semantic": {"facts": clean["facts"], "goal_candidates": old_candidates + clean["goal_candidates"]},
        "procedural": {"preferences": clean["preferences"]},
        "episodic": {"sessions": sorted(sessions, key=lambda s: s["started"])},
        "changes": clean["changes"], "rejected": rejected,
    }
    store.save_dream(user_id, result)
    log.info("dream %s", json.dumps({"user_id": user_id, "sessions": len(new), "facts": len(clean["facts"]),
                                     "preferences": len(clean["preferences"]), "rejected": len(rejected)}))
    return result


def dream_in_background(user_id: str, exclude_session: str | None = None) -> None:
    """Start ``dream`` on a thread (one at a time per user), so signing in never waits for it. Errors are logged."""
    with _running_lock:
        if user_id in _running:
            return
        _running.add(user_id)

    def run():
        try:
            dream(user_id, exclude_session)
        except Exception:
            log.exception("Dreaming failed for %s; the episodes are kept and the next sign-in tries again", user_id)
        finally:
            with _running_lock:
                _running.discard(user_id)

    threading.Thread(target=run, name=f"dream-{user_id}", daemon=True).start()


def main() -> None:
    parser = argparse.ArgumentParser(description="Consolidate users' new episodes into their memory (dreaming).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--user", help="one user, e.g. USR-001")
    group.add_argument("--all", action="store_true", help="every user with unconsolidated episodes")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for user_id in [args.user] if args.user else store.users():
        result = dream(user_id)
        print(f"{user_id}: " + ("nothing new" if result is None else
              f"{len(result['episodic']['sessions'])} sessions, {len(result['semantic']['facts'])} facts, "
              f"{len(result['procedural']['preferences'])} preferences, {len(result['rejected'])} rejected"))


if __name__ == "__main__":
    main()
