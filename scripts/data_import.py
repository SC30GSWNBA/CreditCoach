"""Load the synthetic dataset (``data/users.csv``, ``accounts.csv``, ``score_history.csv``) into Neon Postgres.

Neon holds a copy of the CSVs, which stay the reviewed source: after regenerating the data (``scripts/synthetic/``),
run this again. Each run replaces all three tables in one transaction, so readers see the old data or the new,
never a mix, and running it twice changes nothing. Afterwards it reads Neon back and checks it matches the CSVs
row for row. A running app keeps the data it loaded at start-up; restart it to pick up the new copy.

People who signed up in the app (``creditcoach.signup``) exist only in Neon. Their rows are kept: they are set aside,
the CSVs are loaded, and they are put back after the CSVs' rows, in the order they signed up. The comparison with
the CSVs leaves them out.

Run:
    uv run python scripts/data_import.py --dry-run   # compare Neon with the CSVs, write nothing
    uv run python scripts/data_import.py
"""

import argparse
import sys

from creditcoach import cache, config, dataset
from creditcoach.memory import pg
from creditcoach.signup import store as signups


def reload(conn) -> None:
    """Replace the CSVs' rows in Neon, keeping sign-up users. Runs inside the caller's transaction."""
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('creditcoach_dataset_import'))")
    conn.execute(signups.LOCK)  # nobody can sign up while their rows are set aside
    conn.execute("CREATE TEMP TABLE kept_users ON COMMIT DROP AS SELECT * FROM dataset_users WHERE source = %s",
                 (dataset.SIGNUP_SOURCE,))
    for table in ("accounts", "score_history"):
        conn.execute(f"CREATE TEMP TABLE kept_{table} ON COMMIT DROP AS SELECT t.* FROM dataset_{table} t "
                     "WHERE t.user_id IN (SELECT user_id FROM kept_users)")
    conn.execute("TRUNCATE dataset_score_history, dataset_accounts, dataset_users RESTART IDENTITY")
    for table in dataset.TABLES:  # users first: the other two reference it
        columns = ", ".join(dataset.COLUMNS[table])
        not_null = f", FORCE_NOT_NULL ({columns})" if table == "users" else ""  # blank answers stay ''
        with conn.cursor().copy(f"COPY dataset_{table} ({columns}) FROM STDIN "
                                f"WITH (FORMAT csv, HEADER{not_null})") as copy:
            copy.write((config.DATA_DIR / f"{table}.csv").read_bytes())
    for table in dataset.TABLES:  # sign-ups go back after the CSVs' rows, in their old order
        columns = ", ".join(dataset.COLUMNS[table])
        conn.execute(f"INSERT INTO dataset_{table} ({columns}) SELECT {columns} FROM kept_{table} ORDER BY pos")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="compare Neon with the CSVs, write nothing")
    args = parser.parse_args()
    if not config.DATABASE_URL:
        sys.exit("DATABASE_URL is not set in .env")

    files = dataset.read_files()  # fails early, before touching Neon, if a CSV is missing or malformed
    with pg.pool().connection() as conn:
        dataset.create_schema(conn)
        counts = {t: conn.execute(f"SELECT count(*) FROM dataset_{t}").fetchone()[0] for t in dataset.TABLES}
        signed_up = conn.execute("SELECT count(*) FROM dataset_users WHERE source = %s",
                                 (dataset.SIGNUP_SOURCE,)).fetchone()[0]
    for table, frame in zip(dataset.TABLES, files):
        print(f"  data/{table + '.csv':<18} {len(frame):>4} rows   Neon {counts[table]:>4} rows")
    if signed_up:
        print(f"  Neon also holds {signed_up} sign-up user(s), which are kept and not compared with the CSVs.")
    if args.dry_run:
        stale = dataset.drift() if counts["users"] else list(dataset.TABLES)
        print(f"\nNeon {'differs in ' + ', '.join(stale) if stale else 'already matches the CSVs'}. Nothing written.")
        return

    with pg.pool().connection() as conn, conn.transaction():
        reload(conn)

    stale = dataset.drift()
    if stale:
        sys.exit(f"Imported, but Neon differs from the CSVs in {', '.join(stale)}")
    print(f"\nImported {', '.join(f'{len(f)} {t}' for t, f in zip(dataset.TABLES, files))} rows. "
          "Neon matches the CSVs.")
    cleared = cache.clear("tool") + cache.clear("answer")  # cached lookups and answers were built on the old data
    print(f"Cleared {cleared} cached tool results and answers.")


if __name__ == "__main__":
    main()
