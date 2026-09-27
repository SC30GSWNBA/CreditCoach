"""Per-user logins for the chat UI: each username signs in as exactly one dataset user.

The logins live in ``creditcoach/app/logins.json`` (committed), one entry per username:
``{"user_id": "USR-001", "salt": <hex>, "hash": <hex>}``. Only a salted PBKDF2-SHA256 hash of each password is
stored, so a fresh clone can check logins but the passwords themselves never enter git. Share the passwords
with the team privately. Add or change a login with ``scripts/set_login.py``.

The app passes ``check_login`` to Gradio as its ``auth`` function. After sign-in, ``user_id_for`` maps the
session's username to its user id; that id, never anything the user types, decides whose data is loaded.

Example:
    >>> from creditcoach import auth
    >>> auth.check_login("creditcoach_user1", "wrong password")
    False
    >>> auth.user_id_for("creditcoach_user1")
    'USR-001'
"""

import hashlib
import hmac
import json
import secrets
from functools import lru_cache

from creditcoach import config

ITERATIONS = 200_000


def hash_password(password: str, salt: bytes) -> str:
    """Return the PBKDF2-SHA256 hash of ``password`` with ``salt``, as hex."""
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS).hex()


@lru_cache(maxsize=1)
def logins() -> dict[str, dict]:
    """Read ``logins.json`` once per process. Returns ``{}`` if the file doesn't exist."""
    if not config.LOGINS_FILE.exists():
        return {}
    return json.loads(config.LOGINS_FILE.read_text(encoding="utf-8"))


def check_login(username: str, password: str) -> bool:
    """Return True only if ``username`` exists and ``password`` matches its stored hash.

    The comparison takes the same time whether or not the username exists, so response time doesn't reveal
    which usernames are valid.
    """
    entry = logins().get(username)
    salt = bytes.fromhex(entry["salt"]) if entry else b"\0" * 16
    candidate = hash_password(password or "", salt)
    return entry is not None and hmac.compare_digest(candidate, entry["hash"])


def user_id_for(username: str | None) -> str | None:
    """Return the user id a signed-in username belongs to, or None if the username is unknown."""
    entry = logins().get(username or "")
    return entry["user_id"] if entry else None


def make_entry(user_id: str, password: str) -> dict:
    """Build one ``logins.json`` entry with a fresh random salt."""
    salt = secrets.token_bytes(16)
    return {"user_id": user_id, "salt": salt.hex(), "hash": hash_password(password, salt)}
