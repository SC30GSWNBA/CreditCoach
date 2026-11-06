"""Load the synthetic dataset (``data/users.csv``, ``accounts.csv``, ``score_history.csv``) into Neon Postgres.

Neon holds a copy of the CSVs, which stay the reviewed source: after regenerating the data (``scripts/synthetic/``),
run this again. Each run replaces all three tables in one transaction, so readers see the old data or the new,
never a mix, and running it twice changes nothing. Afterwards it reads Neon back and checks it matches the CSVs
row for row. A running app keeps the data it loaded at start-up; restart it to pick up the new copy.

People who signed up in the app (``creditcoach.signup``) exist only in Neon. Their rows are kept: they are set aside,
the CSVs are loaded, and they are put back after the CSVs' rows, in the order they signed up. If the CSVs now end in
a later month than a sign-up's history (Oct 2026 was added on 2026-11-06), that history is carried on to it, one
month at a time, by the same story it was generated with (``generate.extend``). The comparison with the CSVs leaves
sign-ups out.

Run:
    uv run python scripts/data_import.py --dry-run   # compare Neon with the CSVs, write nothing
    uv run python scripts/data_import.py
"""

import argparse
import sys

from psycopg.rows import dict_row

from creditcoach import cache, config, dataset
from creditcoach.memory import pg
from creditcoach.signup import generate
from creditcoach.signup import store as signups


def reload(conn) -> list[dict]:
    """Replace the CSVs' rows in Neon, keeping sign-up users and bringing them up to the CSVs' latest month
    (``catch_up``). Runs inside the caller's transaction. Returns the sign-ups' added score rows."""
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
    return catch_up(conn)


def catch_up(conn) -> list[dict]:
    """Bring every sign-up's score history up to the CSVs' latest month, one month at a time
    (``generate.extend``), so "now" is the same month for everyone. Returns the rows added."""
    latest = conn.execute("SELECT to_char(max(date), 'YYYY-MM-DD') FROM dataset_score_history "
                          "WHERE user_id NOT IN (SELECT user_id FROM kept_users)").fetchone()[0]
    added = []
    cur = conn.cursor(row_factory=dict_row)
    for u in cur.execute("SELECT * FROM kept_users ORDER BY pos").fetchall():
        rows = cur.execute("SELECT user_id, to_char(date, 'YYYY-MM-DD') AS date, score, primary_factor_change "
                           "FROM kept_score_history WHERE user_id = %s ORDER BY date", (u["user_id"],)).fetchall()
        if not rows:
            continue  # no credit file: nothing to carry on
        accounts = cur.execute("SELECT * FROM kept_accounts WHERE user_id = %s ORDER BY pos", (u["user_id"],)).fetchall()
        while rows[-1]["date"] < latest:
            year, month = int(rows[-1]["date"][:4]), int(rows[-1]["date"][5:7])
            rows.append(generate.extend(u, accounts, rows, f"{year + month // 12}-{month % 12 + 1:02d}-01"))
            added.append(rows[-1])
    columns = ", ".join(dataset.SCORE_COLUMNS)
    for row in added:
        conn.execute(f"INSERT INTO dataset_score_history ({columns}) VALUES (%s, %s, %s, %s)",
                     [row[c] for c in dataset.SCORE_COLUMNS])
    return added


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
        added = reload(conn)

    stale = dataset.drift()
    if stale:
        sys.exit(f"Imported, but Neon differs from the CSVs in {', '.join(stale)}")
    print(f"\nImported {', '.join(f'{len(f)} {t}' for t, f in zip(dataset.TABLES, files))} rows. "
          "Neon matches the CSVs.")
    if added:
        months = sorted({r["date"][:7] for r in added})
        print(f"Brought {len({r['user_id'] for r in added})} sign-up user(s) up to the latest month: {len(added)} "
              f"score row(s) added ({', '.join(months)}).")
    cleared = cache.clear("tool") + cache.clear("answer")  # cached lookups and answers were built on the old data
    print(f"Cleared {cleared} cached tool results and answers.")


if __name__ == "__main__":
    main()
