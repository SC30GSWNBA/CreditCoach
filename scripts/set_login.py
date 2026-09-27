"""Add or change a chat UI login: map a username to one dataset user and store its password hash.

The password is typed at a hidden prompt (twice), so it never appears in shell history or in the repo. Only
a salted hash goes into ``creditcoach/app/logins.json``. Commit that file, then share the password with the
team privately.

Rules enforced:
    - The user id must exist in ``data/users.csv``.
    - A user id has only one username: setting a new username for a user replaces the old one.

Run:
    uv run python scripts/set_login.py USR-005 creditcoach_user5
"""

import getpass
import json
import sys

from creditcoach import auth, config
from creditcoach.user_data import user_ids


def main() -> int:
    """Validate the arguments, prompt for the password, and write the updated logins file."""
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    user_id, username = sys.argv[1], sys.argv[2]
    if user_id not in user_ids():
        print(f"Unknown user id {user_id!r}; see data/users.csv.")
        return 1
    password = getpass.getpass(f"Password for {username} ({user_id}): ")
    if len(password) < 8 or password != getpass.getpass("Repeat password: "):
        print("Passwords didn't match or are shorter than 8 characters; nothing changed.")
        return 1
    current = dict(auth.logins())
    current = {u: e for u, e in current.items() if e["user_id"] != user_id and u != username}
    current[username] = auth.make_entry(user_id, password)
    ordered = dict(sorted(current.items(), key=lambda item: item[1]["user_id"]))
    config.LOGINS_FILE.write_text(json.dumps(ordered, indent=2) + "\n", encoding="utf-8")
    print(f"Saved: {username} -> {user_id} ({len(ordered)} logins in {config.LOGINS_FILE.relative_to(config.ROOT)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
