"""Per-user logins for the chat UI: each username signs in as exactly one dataset user.

The logins live in ``creditcoach/app/logins.json`` (committed), one entry per username:
``{"user_id": "USR-001", "salt": <hex>, "hash": <hex>}``. Only a salted PBKDF2-SHA256 hash of each password is
stored, so a fresh clone can check logins but the passwords themselves never enter git. Share the passwords
with the team privately. Add or change a login with ``scripts/set_login.py``.

People who sign up in the app (``creditcoach.signup``) get a login of the same shape in Neon (``app_logins``),
never in the committed file. ``signup_logins`` reads those; ``check_login`` and ``user_id_for`` accept both kinds.
``is_team`` tells them apart: the 15 committed logins are the team's and have no weekly question limit.

The welcome page (``creditcoach.app.welcome``) checks sign-ins with ``check_login``. After sign-in, ``user_id_for``
maps the session's username to its user id; that id, never anything the user types, decides whose data is loaded.

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
import logging
import secrets
import threading
import time
from functools import lru_cache

from creditcoach import config

log = logging.getLogger(__name__)

ITERATIONS = 200_000
SIGNUP_RELOAD_SECONDS = 30  # how soon an unknown username may trigger another read of Neon's logins


def hash_password(password: str, salt: bytes) -> str:
    """Return the PBKDF2-SHA256 hash of ``password`` with ``salt``, as hex."""
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS).hex()


@lru_cache(maxsize=1)
def logins() -> dict[str, dict]:
    """Read ``logins.json`` once per process: the committed team logins. Returns ``{}`` if the file doesn't exist."""
    if not config.LOGINS_FILE.exists():
        return {}
    return json.loads(config.LOGINS_FILE.read_text(encoding="utf-8"))


_signups: dict = {"entries": {}, "read": 0.0}
_signups_lock = threading.Lock()


def signup_logins(reload: bool = False) -> dict[str, dict]:
    """Logins of people who signed up in the app, from Neon. ``{}`` when the dataset isn't read from Neon.

    Kept in memory after the first read. ``reload=True`` reads again unless that happened in the last
    ``SIGNUP_RELOAD_SECONDS``. If Neon can't be read, the last known logins are returned and the next call retries.

    When a read finds a login this process hadn't seen, its copy of the dataset is dropped too (``forget_dataset``).
    That is the case of someone who signed up on another running copy of the app: their rows are in Neon but not
    in the dataset this process loaded earlier, so without this their header and charts would fail until a restart.
    """
    if config.DATA_BACKEND != "postgres":
        return {}
    with _signups_lock:
        age = time.monotonic() - _signups["read"]
        if not _signups["read"] or (reload and age > SIGNUP_RELOAD_SECONDS):
            from creditcoach.signup import store  # imported here: store imports this module

            try:
                entries = store.logins()
            except Exception:
                log.exception("Couldn't read the sign-up logins from Neon")
            else:
                unseen = set(entries) - set(_signups["entries"])
                _signups["entries"], _signups["read"] = entries, time.monotonic()
                if unseen:
                    forget_dataset()
        return _signups["entries"]


def forget_dataset() -> None:
    """Drop this process's copies of the dataset, so the next read loads users, accounts and scores afresh.

    The MCP tool server needs nothing: it is started fresh for every answer and reads the dataset then.
    """
    from creditcoach import user_data  # imported here: neither is needed just to check a login
    from creditcoach.tools import common

    common.tables.cache_clear()
    user_data._tables.cache_clear()


def forget_signup_logins() -> None:
    """Read the sign-up logins from Neon again on the next call (called after a sign-up)."""
    with _signups_lock:
        _signups["read"] = 0.0


def entry_for(username: str | None) -> dict | None:
    """The login entry for ``username``: a team login from the file, else a sign-up login from Neon, else None."""
    username = username or ""
    entry = logins().get(username)
    if entry is None and username:
        entry = signup_logins().get(username) or signup_logins(reload=True).get(username)
    return entry


def is_team(username: str | None) -> bool:
    """Whether ``username`` is one of the committed team logins (the 15 original users)."""
    return (username or "") in logins()


def check_login(username: str, password: str) -> bool:
    """Return True only if ``username`` exists and ``password`` matches its stored hash.

    The comparison takes the same time whether or not the username exists, so response time doesn't reveal
    which usernames are valid.
    """
    entry = entry_for(username)
    salt = bytes.fromhex(entry["salt"]) if entry else b"\0" * 16
    candidate = hash_password(password or "", salt)
    return entry is not None and hmac.compare_digest(candidate, entry["hash"])


def user_id_for(username: str | None) -> str | None:
    """Return the user id a signed-in username belongs to, or None if the username is unknown."""
    entry = entry_for(username)
    return entry["user_id"] if entry else None


def make_entry(user_id: str, password: str) -> dict:
    """Build one ``logins.json`` entry with a fresh random salt."""
    salt = secrets.token_bytes(16)
    return {"user_id": user_id, "salt": salt.hex(), "hash": hash_password(password, salt)}
