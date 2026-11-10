"""Sign-in sessions for the chat UI: a signed cookie that says which username a browser is signed in as.

Gradio's built-in login page can't hold a "Sign up" tab, so the welcome page (``creditcoach.app.welcome``) checks
the username and password itself and this module remembers the result:

    Ticket   A Gradio event can't set a cookie, so a successful login returns a random one-time ticket. The browser
             then opens ``/auth/enter?t=<ticket>`` (``creditcoach.app.server``), which swaps it for the cookie. A
             ticket works once, for 30 seconds, and never contains the password.
    Cookie   ``username|expiry|HMAC-SHA256``, HttpOnly. ``current_user`` returns the username only if the signature
             is ours, it hasn't expired, and the login still exists. Gradio calls it for every request
             (``auth_dependency``) and puts the result in ``request.username``, where the app has always read it.

Failed logins are limited per username (``too_many_failures``), since each sign-up login is one guessable name.

The admin (``creditcoach.admin``) has a cookie of its own, ``ADMIN_COOKIE``, sent only to ``/admin`` paths:
``admin|expiry|epoch|HMAC-SHA256``. ``epoch`` is when the admin password was last set, so a new password signs out
every admin session made before it. A user's cookie never opens the admin page, and the admin's never opens the chat.
"""

import hashlib
import hmac
import secrets
import threading
import time

from creditcoach import admin, auth, config

COOKIE = "creditcoach_session"
SESSION_SECONDS = 7 * 24 * 3600
TICKET_SECONDS = 30
MAX_FAILURES, FAILURE_WINDOW = 8, 15 * 60  # failed logins allowed per username per 15 minutes
ADMIN_COOKIE, ADMIN_SECONDS = "creditcoach_admin", 12 * 3600
ADMIN = "admin"  # the admin page's ``request.username`` (no dataset username is spelled this way)
ADMIN_FAILURES = 5  # failed admin sign-ins allowed per 15 minutes

_secret = config.SESSION_SECRET.encode() or secrets.token_bytes(32)
_lock = threading.Lock()
_tickets: dict[str, tuple[str, str, float]] = {}  # ticket -> (kind, username, expiry)
_failures: dict[str, list[float]] = {}


def _mac(body: str) -> str:
    return hmac.new(_secret, body.encode(), hashlib.sha256).hexdigest()


def cookie_for(username: str, now: float | None = None) -> str:
    """The cookie value that signs a browser in as ``username`` for ``SESSION_SECONDS``."""
    body = f"{username}|{int((now or time.time()) + SESSION_SECONDS)}"
    return f"{body}|{_mac(body)}"


def username_in(value: str | None, now: float | None = None) -> str | None:
    """The username a cookie value was issued for, or None if it is missing, altered, expired or its login is gone."""
    try:
        username, expires, mac = (value or "").rsplit("|", 2)
        expired = int(expires) < (now or time.time())
    except ValueError:
        return None
    if expired or not hmac.compare_digest(mac, _mac(f"{username}|{expires}")):
        return None
    return username if auth.user_id_for(username) else None


def current_user(request) -> str | None:
    """The signed-in username for a request: what Gradio's ``auth_dependency`` expects."""
    return username_in(request.cookies.get(COOKIE))


def issue_ticket(username: str, kind: str = "user") -> str:
    """A one-time ticket that ``redeem_ticket`` swaps for ``username`` within ``TICKET_SECONDS``. ``kind`` is "user"
    (``/auth/enter``) or "admin" (``/admin/enter``); a ticket only works where its kind is redeemed."""
    ticket = secrets.token_urlsafe(32)
    with _lock:
        now = time.time()
        for old in [t for t, (_, _, expires) in _tickets.items() if expires < now]:
            del _tickets[old]
        _tickets[ticket] = (kind, username, now + TICKET_SECONDS)
    return ticket


def redeem_ticket(ticket: str, kind: str = "user") -> str | None:
    """The username a ticket of ``kind`` was issued for, once; None if it is unknown, used, expired or of the
    other kind."""
    with _lock:
        found = _tickets.get(ticket)
        if not found or found[0] != kind:
            return None
        del _tickets[ticket]
    return found[1] if found[2] >= time.time() else None


def admin_cookie(now: float | None = None) -> str:
    """The cookie value that signs a browser in as the admin for ``ADMIN_SECONDS``, under the current password."""
    body = f"{ADMIN}|{int((now or time.time()) + ADMIN_SECONDS)}|{admin.epoch()}"
    return f"{body}|{_mac('admin-cookie|' + body)}"


def admin_in(value: str | None, now: float | None = None) -> bool:
    """Whether a cookie value is a live admin session: ours, not expired, and made under the current password."""
    try:
        name, expires, epoch, mac = (value or "").split("|")
        expired = int(expires) < (now or time.time())
    except ValueError:
        return False
    if name != ADMIN or expired or not hmac.compare_digest(mac, _mac(f"admin-cookie|{name}|{expires}|{epoch}")):
        return False
    try:
        current = admin.epoch()
    except Exception:  # the stored login can't be read: no admin page until it can
        return False
    return current is not None and epoch == current


def current_admin(request) -> str | None:
    """``ADMIN`` for a request from a signed-in admin, else None: the admin page's ``auth_dependency``."""
    return ADMIN if admin_in(request.cookies.get(ADMIN_COOKIE)) else None


def too_many_failures(username: str, limit: int = MAX_FAILURES) -> bool:
    """Whether ``username`` has had ``limit`` failed logins in the last ``FAILURE_WINDOW`` seconds."""
    with _lock:
        recent = [t for t in _failures.get(username, []) if t > time.time() - FAILURE_WINDOW]
        _failures[username] = recent
        return len(recent) >= limit


def recent_failures(username: str) -> int:
    """How many failed logins ``username`` has had in the last ``FAILURE_WINDOW`` seconds."""
    with _lock:
        return sum(t > time.time() - FAILURE_WINDOW for t in _failures.get(username, []))


def note_failure(username: str) -> None:
    """Record one failed login for ``username`` (names are capped so junk can't grow the table without bound)."""
    with _lock:
        if len(_failures) > 5000:
            _failures.clear()
        _failures.setdefault(username[:64], []).append(time.time())
