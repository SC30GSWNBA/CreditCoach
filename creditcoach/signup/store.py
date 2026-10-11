"""Save a sign-up to Neon: the new user, their accounts and score history, and their login.

A sign-up adds rows to the three dataset tables (``dataset_users``, ``dataset_accounts``,
``dataset_score_history``; ``creditcoach.dataset``) with ``source = 'Sign-up'``, and one row to ``app_logins``:

    app_logins  username (``creditcoach_userN``) -> user id, with the salt and PBKDF2 hash of the password, exactly
                what ``creditcoach/app/logins.json`` holds for the 15 original users. The password is never stored.

Everything for one sign-up is written in a single transaction, under an advisory lock, so two people signing up
at the same moment can't get the same number and a failed sign-up leaves nothing behind. ``N`` is the number of
users already in Neon plus one: with 15 users the next is ``creditcoach_user16`` / ``USR-016``.

Sign-up needs Neon (``config.DATA_BACKEND == "postgres"``): ``data/*.csv`` and ``logins.json`` are the reviewed,
committed copies of the original 15 and are never written by the app. ``scripts/data_import.py`` keeps sign-up rows
when it reloads the CSVs, and ``dataset.drift`` ignores them.
"""

import logging
import threading

from creditcoach import auth, config, dataset
from creditcoach.signup import generate

log = logging.getLogger(__name__)

LOCK = "SELECT pg_advisory_xact_lock(hashtext('creditcoach_signup'))"  # also taken by scripts/data_import.py
SCHEMA = """
CREATE TABLE IF NOT EXISTS app_logins (
    username  text PRIMARY KEY CHECK (username ~ '^creditcoach_user[0-9]+$'),
    user_id   text NOT NULL UNIQUE CHECK (user_id ~ '^USR-[0-9]{3}$'),
    salt      text NOT NULL,
    hash      text NOT NULL,
    created   timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS app_usage (
    user_id     text PRIMARY KEY CHECK (user_id ~ '^USR-[0-9]{3}$'),
    week_start  timestamptz NOT NULL,
    asked       integer NOT NULL CHECK (asked >= 0)
);
"""

_ready = threading.Event()


class SignupUnavailable(Exception):
    """Sign-up can't be offered: there is no Neon database behind this app."""


class SignupClosed(Exception):
    """No more sign-ups are being accepted (``config.SIGNUP_MAX`` reached, or user ids have run out)."""


def available() -> bool:
    """Whether this app can create accounts (it reads its dataset from Neon)."""
    return config.DATA_BACKEND == "postgres" and bool(config.DATABASE_URL)


def connection():
    """A pooled Neon connection, with the dataset and app tables created on first use."""
    from creditcoach.memory import pg  # the shared pool; imported only when Neon is used

    conn = pg.pool().connection()
    if not _ready.is_set():
        with pg.pool().connection() as first:
            dataset.create_schema(first)
            with first.transaction():
                first.execute("SELECT pg_advisory_xact_lock(hashtext('creditcoach_app_schema'))")
                first.execute(SCHEMA)
        _ready.set()
    return conn


def logins() -> dict[str, dict]:
    """Every sign-up login in Neon, in the shape of ``logins.json`` entries. ``{}`` when sign-up isn't available."""
    if not available():
        return {}
    with connection() as conn:
        rows = conn.execute("SELECT username, user_id, salt, hash FROM app_logins").fetchall()
    return {username: {"user_id": user_id, "salt": salt, "hash": hash_} for username, user_id, salt, hash_ in rows}


def insert(conn, answers: dict) -> dict:
    """Create one user on ``conn``, inside the caller's transaction (``create_account`` commits it).

    Returns:
        ``{"username", "user_id", "password", "scenario", "accounts", "scores"}``; the last two are row counts.

    Raises:
        SignupClosed: The sign-up limit is reached.
        RuntimeError: The generated data failed validation (nothing is written).
    """
    conn.execute(LOCK)
    total, signed_up = conn.execute("SELECT count(*), count(*) FILTER (WHERE source = %s) FROM dataset_users",
                                    (dataset.SIGNUP_SOURCE,)).fetchone()
    if signed_up >= config.SIGNUP_MAX or total >= 999:  # user ids are USR-001 to USR-999
        raise SignupClosed(f"{signed_up} sign-ups, limit {config.SIGNUP_MAX}")
    n = total + 1
    user_id, username = f"USR-{n:03d}", f"creditcoach_user{n}"
    last_account, latest = conn.execute(
        "SELECT (SELECT coalesce(max(substring(account_id FROM '[0-9]+$')::int), 0) FROM dataset_accounts), "
        "(SELECT to_char(max(date), 'YYYY-MM-DD') FROM dataset_score_history)").fetchone()
    counter = iter(range(last_account + 1, last_account + 100))

    user = generate.user_row(user_id, answers)
    accounts = generate.build_accounts(user, lambda: f"ACC-{next(counter):02d}")
    scenario, scores = generate.build_scores(user, accounts, generate.months_ending(latest))
    errors = generate.problems(user, accounts, scores)
    if errors:
        raise RuntimeError(f"generated data for {user_id} failed validation: {'; '.join(errors)}")
    password = generate.new_password()
    entry = auth.make_entry(user_id, password)

    def add(table: str, columns: list[str], rows: list[dict]) -> None:
        for row in rows:
            conn.execute(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})",
                         [row[c] for c in columns])

    add("dataset_users", dataset.USER_COLUMNS, [user])
    add("dataset_accounts", dataset.ACCOUNT_COLUMNS, accounts)
    add("dataset_score_history", dataset.SCORE_COLUMNS, scores)
    conn.execute("INSERT INTO app_logins (username, user_id, salt, hash) VALUES (%s, %s, %s, %s)",
                 (username, user_id, entry["salt"], entry["hash"]))
    return {"username": username, "user_id": user_id, "password": password, "scenario": scenario,
            "accounts": len(accounts), "scores": len(scores)}


def refresh_caches() -> None:
    """Make this process see a user who has just signed up: its copies of the dataset and of the sign-up logins.

    Another running copy of the app catches up by itself the first time it sees the new login
    (``auth.signup_logins``).
    """
    auth.forget_dataset()
    auth.forget_signup_logins()


def create_account(answers: dict) -> dict:
    """Create a user from cleaned sign-up answers (``questions.clean``) and return their login, password included.

    The password is returned once, to be shown to the person, and is not stored or logged anywhere.

    Raises:
        SignupUnavailable: This app has no Neon database.
        SignupClosed: The sign-up limit is reached.
    """
    if not available():
        raise SignupUnavailable("sign-up needs the Neon database (DATABASE_URL)")
    with connection() as conn, conn.transaction():
        made = insert(conn, answers)
    refresh_caches()
    log.info("Sign-up: %s (%s), %d accounts, %d score rows, scenario: %s", made["username"], made["user_id"],
             made["accounts"], made["scores"], made["scenario"])
    return made
