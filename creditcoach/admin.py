"""The admin login: one email address and password that open the full Dashboard for every user.

The admin signs in at ``/admin`` (``creditcoach.app.admin_page``), never on the welcome page, and is not one of the
dataset's users: the admin sees the Dashboard only, for all users or for any one of them.

    Where the password lives   Neon, table ``app_admin``: the salted PBKDF2 hash (``auth.hash_password``), never
                               the password. The first start with ``CREDITCOACH_ADMIN_PASSWORD`` set and no row yet
                               stores that password's hash; after that the stored hash wins, so a password changed in
                               the app survives redeploys. Without Neon the hash is kept in memory, from the same
                               setting, and a change lasts until the app restarts.
    Changing it                ``change``: the current password, then a new one of at least ``MIN_LENGTH``
                               characters, typed twice. The caller emails the new password to ``EMAIL``.
    Forgotten                  ``start_reset`` makes a one-time link valid for ``RESET_SECONDS``; only its SHA-256
                               is stored, and asking again replaces it. ``finish_reset`` sets the new password.
                               At most ``MAX_RESETS`` links an hour, so the inbox can't be flooded.
    Signed-in sessions         ``epoch`` changes with every new password, and the admin cookie carries it
                               (``app.sessions``), so a new password signs out every other admin session.

Example:
    >>> from creditcoach import admin
    >>> admin.check(admin.EMAIL, "wrong password")
    False
"""

import hashlib
import hmac
import logging
import secrets
import threading
import time
from datetime import UTC, datetime

from creditcoach import auth, config

log = logging.getLogger(__name__)

EMAIL = config.ADMIN_EMAIL
MIN_LENGTH = 12
RESET_SECONDS = 30 * 60
MAX_RESETS, RESET_WINDOW = 3, 3600
EPOCH_SECONDS = 10  # how long a read of the stored epoch is trusted, since every admin request checks it

SCHEMA = """
CREATE TABLE IF NOT EXISTS app_admin (
    email          text PRIMARY KEY,
    salt           text NOT NULL,
    hash           text NOT NULL,
    changed        timestamptz NOT NULL DEFAULT now(),
    reset_hash     text,
    reset_expires  timestamptz
);
"""


class AdminError(Exception):
    """A change or reset that can't be made; the message says why, in words the admin can act on."""


_lock = threading.Lock()
_memory: dict = {}  # the row, when there is no Neon
_epoch: dict = {"value": None, "read": 0.0}
_resets: list[float] = []
_ready = threading.Event()


def _neon() -> bool:
    from creditcoach.signup import store  # imported here: store imports auth, which this module also uses

    return store.available()


def _connection():
    from creditcoach.signup import store

    conn = store.connection()
    if not _ready.is_set():
        with store.connection() as first:
            first.execute(SCHEMA)
        _ready.set()
    return conn


def _row() -> dict | None:
    """The stored login, seeded from ``CREDITCOACH_ADMIN_PASSWORD`` when there is none yet; None if neither."""
    if not _neon():
        with _lock:
            if not _memory and config.ADMIN_PASSWORD:
                _memory.update(_fresh(config.ADMIN_PASSWORD))
            return dict(_memory) or None
    with _connection() as conn:
        found = conn.execute("SELECT salt, hash, changed, reset_hash, reset_expires FROM app_admin WHERE email = %s",
                             (EMAIL,)).fetchone()
        if found is None and config.ADMIN_PASSWORD:
            seed = _fresh(config.ADMIN_PASSWORD)
            conn.execute("INSERT INTO app_admin (email, salt, hash) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                         (EMAIL, seed["salt"], seed["hash"]))
            found = conn.execute("SELECT salt, hash, changed, reset_hash, reset_expires FROM app_admin "
                                 "WHERE email = %s", (EMAIL,)).fetchone()
    if found is None:
        return None
    salt, hash_, changed, reset_hash, reset_expires = found
    return {"salt": salt, "hash": hash_, "changed": changed, "reset_hash": reset_hash, "reset_expires": reset_expires}


def _fresh(password: str) -> dict:
    entry = auth.make_entry("admin", password)
    return {"salt": entry["salt"], "hash": entry["hash"], "changed": datetime.now(UTC), "reset_hash": None,
            "reset_expires": None}


def _save(password: str) -> None:
    """Store ``password``'s hash with a new ``changed`` time, and drop any reset link."""
    new = _fresh(password)
    if _neon():
        with _connection() as conn:
            conn.execute("UPDATE app_admin SET salt = %s, hash = %s, changed = now(), reset_hash = NULL, "
                         "reset_expires = NULL WHERE email = %s", (new["salt"], new["hash"], EMAIL))
    else:
        with _lock:
            _memory.update(new)
    with _lock:
        _epoch["read"] = 0.0


def configured() -> bool:
    """Whether there is an admin password to sign in with."""
    try:
        return _row() is not None
    except Exception:
        log.exception("Couldn't read the admin login")
        return False


def _matches(row: dict | None, password: str) -> bool:
    salt = bytes.fromhex(row["salt"]) if row else b"\0" * 16
    candidate = auth.hash_password(password or "", salt)
    return row is not None and hmac.compare_digest(candidate, row["hash"])


def check(email: str, password: str) -> bool:
    """True only for the admin email (any letter case) with its current password."""
    row = _row()
    right_email = hmac.compare_digest((email or "").strip().lower().encode(), EMAIL.lower().encode())
    return _matches(row, password) and right_email


def epoch() -> str | None:
    """When the password was last set, as text: part of every admin cookie. None if there is no admin login."""
    with _lock:
        if time.monotonic() - _epoch["read"] < EPOCH_SECONDS:
            return _epoch["value"]
    row = _row()
    value = row["changed"].isoformat() if row else None
    with _lock:
        _epoch.update(value=value, read=time.monotonic())
    return value


def _check_new(new: str, confirm: str) -> None:
    if len(new or "") < MIN_LENGTH:
        raise AdminError(f"The new password needs at least {MIN_LENGTH} characters.")
    if new != confirm:
        raise AdminError("The two new passwords don't match. Type the same password in both boxes.")


def change(current: str, new: str, confirm: str) -> None:
    """Set a new password after checking the current one. Raises ``AdminError`` saying what to fix."""
    row = _row()
    if not _matches(row, current):
        raise AdminError("The current password isn't right.")
    _check_new(new, confirm)
    if _matches(row, new):
        raise AdminError("The new password is the same as the current one. Choose a different one.")
    _save(new)


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_reset() -> str:
    """A new one-time reset token (it goes in the emailed link), replacing any earlier one.

    Raises:
        AdminError: No admin login is set up, or ``MAX_RESETS`` links were asked for in the last hour.
    """
    with _lock:
        now = time.time()
        _resets[:] = [t for t in _resets if t > now - RESET_WINDOW]
        if len(_resets) >= MAX_RESETS:
            raise AdminError("Too many reset links were asked for. Please wait an hour and try again.")
        _resets.append(now)
    if _row() is None:
        raise AdminError("There is no admin login to reset.")
    token = secrets.token_urlsafe(32)
    expires = datetime.fromtimestamp(time.time() + RESET_SECONDS, UTC)
    if _neon():
        with _connection() as conn:
            conn.execute("UPDATE app_admin SET reset_hash = %s, reset_expires = %s WHERE email = %s",
                         (_digest(token), expires, EMAIL))
    else:
        with _lock:
            _memory.update(reset_hash=_digest(token), reset_expires=expires)
    return token


def reset_valid(token: str) -> bool:
    """Whether ``token`` is the current reset link's and hasn't expired."""
    row = _row()
    if not (row and row["reset_hash"] and token):
        return False
    return hmac.compare_digest(_digest(token), row["reset_hash"]) and row["reset_expires"] > datetime.now(UTC)


def finish_reset(token: str, new: str, confirm: str) -> None:
    """Set a new password from a reset link, which then stops working. Raises ``AdminError`` saying what to fix."""
    if not reset_valid(token):
        raise AdminError("This reset link has expired or was already used. Ask for a new one.")
    _check_new(new, confirm)
    _save(new)
