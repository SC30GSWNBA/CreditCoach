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
"""

import hashlib
import hmac
import secrets
import threading
import time

from creditcoach import auth, config

COOKIE = "creditcoach_session"
SESSION_SECONDS = 7 * 24 * 3600
TICKET_SECONDS = 30
MAX_FAILURES, FAILURE_WINDOW = 8, 15 * 60  # failed logins allowed per username per 15 minutes

_secret = config.SESSION_SECRET.encode() or secrets.token_bytes(32)
_lock = threading.Lock()
_tickets: dict[str, tuple[str, float]] = {}
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


def issue_ticket(username: str) -> str:
    """A one-time ticket that ``redeem_ticket`` swaps for ``username`` within ``TICKET_SECONDS``."""
    ticket = secrets.token_urlsafe(32)
    with _lock:
        now = time.time()
        for old in [t for t, (_, expires) in _tickets.items() if expires < now]:
            del _tickets[old]
        _tickets[ticket] = (username, now + TICKET_SECONDS)
    return ticket


def redeem_ticket(ticket: str) -> str | None:
    """The username a ticket was issued for, once; None if it is unknown, used or expired."""
    with _lock:
        username, expires = _tickets.pop(ticket, (None, 0.0))
    return username if username and expires >= time.time() else None


def too_many_failures(username: str) -> bool:
    """Whether ``username`` has had ``MAX_FAILURES`` failed logins in the last ``FAILURE_WINDOW`` seconds."""
    with _lock:
        recent = [t for t in _failures.get(username, []) if t > time.time() - FAILURE_WINDOW]
        _failures[username] = recent
        return len(recent) >= MAX_FAILURES


def note_failure(username: str) -> None:
    """Record one failed login for ``username`` (names are capped so junk can't grow the table without bound)."""
    with _lock:
        if len(_failures) > 5000:
            _failures.clear()
        _failures.setdefault(username[:64], []).append(time.time())
