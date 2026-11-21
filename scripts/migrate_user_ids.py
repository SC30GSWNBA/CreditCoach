"""Let Neon's tables hold 4-digit user ids (USR-1000 and on), for sign-ups past the 999th.

User ids were 3 digits until 2026-11-21, and five tables check that: ``dataset_users``, ``app_logins``,
``app_usage``, ``memory_events`` and ``memory_dreams``. Their ``CREATE TABLE IF NOT EXISTS`` statements now allow
3 or 4 digits, but a table that already exists keeps its old check, so this replaces it, in one transaction. Every
existing id (USR-001 to USR-999) passes the new check, so no row changes. Running it twice changes nothing.

Run:
    uv run python scripts/migrate_user_ids.py --dry-run   # show each table's check, change nothing
    uv run python scripts/migrate_user_ids.py
"""

import argparse

import psycopg

from creditcoach import config

TABLES = ("dataset_users", "app_logins", "app_usage", "memory_events", "memory_dreams")
NEW_CHECK = "CHECK (user_id ~ '^USR-[0-9]{3,4}$')"
# Each table's user-id check, as Postgres prints it (constraint name, definition)
FIND = """
SELECT c.conname, pg_get_constraintdef(c.oid)
FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
WHERE t.relname = %s AND c.contype = 'c' AND pg_get_constraintdef(c.oid) LIKE '%%USR-%%'
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="show each table's check, change nothing")
    args = parser.parse_args()

    with psycopg.connect(config.DATABASE_URL, prepare_threshold=None) as conn, conn.transaction():
        for table in TABLES:
            checks = conn.execute(FIND, (table,)).fetchall()
            if not checks:
                print(f"{table}: no user-id check (table missing?), skipped")
                continue
            for name, definition in checks:
                if "{3,4}" in definition:
                    print(f"{table}: {name} already allows 4 digits")
                    continue
                print(f"{table}: {name} {definition} -> {NEW_CHECK}")
                if not args.dry_run:
                    conn.execute(f'ALTER TABLE {table} DROP CONSTRAINT "{name}"')
                    conn.execute(f'ALTER TABLE {table} ADD CONSTRAINT "{name}" {NEW_CHECK}')
        if args.dry_run:
            print("Dry run: nothing changed.")


if __name__ == "__main__":
    main()
