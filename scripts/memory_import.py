"""Copy the file memory archive (``memory/<user_id>/``) into Neon Postgres.

Safe to run more than once, and by every teammate: an episode whose session is already in Neon is skipped, and
a dream keeps its file name as its id, so it is inserted only once. Files are only read, never changed or removed;
they stay in git as the archive from before the move. Run it on a machine with sessions that never reached git to
bring those into Neon too.

Run:
    uv run python scripts/memory_import.py --dry-run   # list what isn't in Neon yet, write nothing
    uv run python scripts/memory_import.py
"""

import argparse
import json
import sys
from dataclasses import asdict

from creditcoach import config
from creditcoach.memory import pg, store


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="list what isn't in Neon yet, write nothing")
    args = parser.parse_args()
    if not config.DATABASE_URL:
        sys.exit("DATABASE_URL is not set in .env")

    stored_sessions, stored_dreams = pg.stored_ids() if args.dry_run else (set(), set())
    config.MEMORY_BACKEND = "files"  # read the archive through the files backend
    users = store.users()
    episodes = dreams = 0
    for user_id in users:
        base = store.user_dir(user_id)
        for path in sorted((base / "episodes").glob("*.jsonl")):
            events = [asdict(e) for e in store.read_episode(path).events if e.user_id == user_id]
            new = path.stem not in stored_sessions if args.dry_run else pg.import_episode(events)
            episodes += new
            print(f"  {('would import' if args.dry_run else 'imported') if new else 'already in Neon'}  "
                  f"{path.relative_to(config.ROOT)} ({len(events)} events)")
        for path in sorted((base / "dreams").glob("*.json")):
            try:
                body = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                print(f"  skipped (not valid JSON)  {path.relative_to(config.ROOT)}")
                continue
            if body.get("user_id") != user_id or not body.get("created"):
                print(f"  skipped (wrong user or no 'created')  {path.relative_to(config.ROOT)}")
                continue
            new = path.stem not in stored_dreams if args.dry_run else pg.save_dream(path.stem, user_id, body["created"], body)
            dreams += new
            print(f"  {('would import' if args.dry_run else 'imported') if new else 'already in Neon'}  "
                  f"{path.relative_to(config.ROOT)}")
    if args.dry_run:
        print(f"\nWould import {episodes} episode(s) and {dreams} dream(s). Nothing written.")
    else:
        print(f"\nImported {episodes} episode(s) and {dreams} dream(s) for {len(users)} user(s). "
              f"Neon now holds {pg.session_count()} session(s).")


if __name__ == "__main__":
    main()
