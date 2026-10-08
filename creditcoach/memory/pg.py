"""Neon Postgres storage for per-user memory: the "postgres" backend behind ``creditcoach.memory.store``.

Two tables hold what the "files" backend keeps under ``memory/<user_id>/`` (schema: docs/memory.md §2):

    memory_events  One row per episode event (an episode is every row with the same ``session``). Replaces
                   ``episodes/<session>.jsonl``; ``id`` keeps the order events were written.
    memory_dreams  One row per consolidated memory, the whole dream as JSONB. Replaces ``dreams/<id>.json``; the
                   newest ``created`` is current.

Both are append-only, like the files: a trigger refuses every UPDATE and DELETE, so a bug or a bad query can't
rewrite what a user said. To remove something real typed by mistake (§8), the project owner disables the trigger
in the Neon SQL editor, deletes the rows, and enables it again.

The tables are created on first use. ``store`` calls this module only when ``config.MEMORY_BACKEND`` is
"postgres"; nothing here is imported otherwise, so tests need neither the driver nor a database.
"""

import threading

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from creditcoach import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_events (
    id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    v        integer     NOT NULL,
    ts       timestamptz NOT NULL,
    user_id  text        NOT NULL CHECK (user_id ~ '^USR-[0-9]{3}$'),
    session  text        NOT NULL,
    type     text        NOT NULL CHECK (type IN ('login', 'user_message', 'assistant_message', 'error',
                                                  'goal_set', 'goal_cleared', 'logout', 'session_end')),
    text     text        NOT NULL DEFAULT '',
    meta     jsonb       NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS memory_events_user_ts ON memory_events (user_id, ts, id);
CREATE INDEX IF NOT EXISTS memory_events_session ON memory_events (session);

CREATE TABLE IF NOT EXISTS memory_dreams (
    id       text        PRIMARY KEY,
    user_id  text        NOT NULL CHECK (user_id ~ '^USR-[0-9]{3}$'),
    created  timestamptz NOT NULL,
    body     jsonb       NOT NULL
);
CREATE INDEX IF NOT EXISTS memory_dreams_user_created ON memory_dreams (user_id, created DESC, id DESC);

CREATE OR REPLACE FUNCTION memory_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'memory is append-only: % on % is not allowed', TG_OP, TG_TABLE_NAME;
END $$;
CREATE OR REPLACE TRIGGER memory_events_append_only BEFORE UPDATE OR DELETE ON memory_events
    FOR EACH ROW EXECUTE FUNCTION memory_append_only();
CREATE OR REPLACE TRIGGER memory_dreams_append_only BEFORE UPDATE OR DELETE ON memory_dreams
    FOR EACH ROW EXECUTE FUNCTION memory_append_only();
"""

# Timestamps go in as the store's ISO strings and come back in exactly that form (millisecond precision, "Z").
TS = """to_char({col} AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')"""

_lock = threading.Lock()
_pools: dict[str, ConnectionPool] = {}


def pool() -> ConnectionPool:
    """The process's connection pool for ``config.DATABASE_URL``, opened (and the schema created) on first use.

    Neon suspends an idle database after 5 minutes and drops its connections, so each connection is checked before
    it is handed out. ``prepare_threshold=None`` keeps psycopg from using prepared statements, which Neon's pooled
    (PgBouncer) endpoint doesn't support.
    """
    url = config.DATABASE_URL
    if not url:
        raise RuntimeError("a Neon (postgres) backend is selected but DATABASE_URL is not set in .env")
    with _lock:
        if url not in _pools:
            p = ConnectionPool(url, min_size=1, max_size=4, open=True, check=ConnectionPool.check_connection,
                               kwargs={"autocommit": True, "prepare_threshold": None, "connect_timeout": 15})
            with p.connection() as conn, conn.transaction():
                conn.execute("SELECT pg_advisory_xact_lock(hashtext('creditcoach_memory_schema'))")
                conn.execute(SCHEMA)
            _pools[url] = p
        return _pools[url]


# ---- Writing ----

def append_event(event: dict) -> None:
    """Insert one event (the store's ``Event`` as a dict)."""
    with pool().connection() as conn:
        conn.execute("INSERT INTO memory_events (v, ts, user_id, session, type, text, meta) "
                     "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                     (event["v"], event["ts"], event["user_id"], event["session"], event["type"], event["text"],
                      Jsonb(event["meta"])))


def save_dream(dream_id: str, user_id: str, created: str, body: dict) -> bool:
    """Insert one dream; returns False if a dream with this id is already stored (nothing is overwritten)."""
    with pool().connection() as conn:
        cur = conn.execute("INSERT INTO memory_dreams (id, user_id, created, body) VALUES (%s, %s, %s, %s) "
                           "ON CONFLICT (id) DO NOTHING", (dream_id, user_id, created, Jsonb(body)))
        return cur.rowcount == 1


def import_episode(events: list[dict]) -> bool:
    """Insert a whole episode in one transaction, unless its session is already stored (for the archive import).

    Returns:
        True if the episode was inserted, False if it was already there.
    """
    if not events:
        return False
    session = events[0]["session"]
    with pool().connection() as conn, conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (session,))
        if conn.execute("SELECT 1 FROM memory_events WHERE session = %s LIMIT 1", (session,)).fetchone():
            return False
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO memory_events (v, ts, user_id, session, type, text, meta) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                            [(e["v"], e["ts"], e["user_id"], e["session"], e["type"], e["text"], Jsonb(e["meta"]))
                             for e in events])
    return True


# ---- Reading ----

def events(user_id: str) -> list[dict]:
    """Every event of one user, in the order it happened (and, within a millisecond, the order it was written)."""
    with pool().connection() as conn:
        rows = conn.execute(f"SELECT v, {TS.format(col='ts')}, user_id, session, type, text, meta "
                            "FROM memory_events WHERE user_id = %s ORDER BY ts, id", (user_id,)).fetchall()
    keys = ("v", "ts", "user_id", "session", "type", "text", "meta")
    return [dict(zip(keys, r)) for r in rows]


def latest_dream(user_id: str) -> dict | None:
    """The newest dream of one user, or None."""
    with pool().connection() as conn:
        row = conn.execute("SELECT body FROM memory_dreams WHERE user_id = %s ORDER BY created DESC, id DESC LIMIT 1",
                           (user_id,)).fetchone()
    return row[0] if row else None


def stored_ids() -> tuple[set[str], set[str]]:
    """The session ids and dream ids already stored (read-only; for the archive import's dry run)."""
    with pool().connection() as conn:
        sessions = {r[0] for r in conn.execute("SELECT DISTINCT session FROM memory_events").fetchall()}
        dreams = {r[0] for r in conn.execute("SELECT id FROM memory_dreams").fetchall()}
    return sessions, dreams


def users() -> list[str]:
    """User ids with any stored memory."""
    with pool().connection() as conn:
        rows = conn.execute("SELECT user_id FROM memory_events UNION SELECT user_id FROM memory_dreams "
                            "ORDER BY 1").fetchall()
    return [r[0] for r in rows]


def session_count() -> int:
    """Number of stored episodes, across all users."""
    with pool().connection() as conn:
        return conn.execute("SELECT count(DISTINCT session) FROM memory_events").fetchone()[0]

