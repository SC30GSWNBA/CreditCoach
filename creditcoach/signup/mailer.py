"""Email a new login to the person who just signed up (the optional backup for the one-time password pop-up), and
the admin's password emails: a changed password, and a reset link (``creditcoach.app.admin_page``).

The message is sent once, straight after sign-up, with the User ID and password the pop-up shows. The address is
used for that one message and is not stored or logged. CreditCoach keeps only a hash of the password, so this
email (or the person's own copy) is the only record of it.

It needs a way to send mail in ``.env`` (see ``.env.example``). Without one, ``configured()`` is False and the pop-up
leaves the email option out. Either:

    BREVO_API_KEY       Brevo's email API, over HTTPS. Use it on Railway: its Free, Trial and Hobby plans block
                        outgoing SMTP (ports 25, 465 and 587), so an SMTP send there times out. The sender is
                        ``SMTP_FROM`` (else ``SMTP_USER``), and must be a sender confirmed in Brevo.
    SMTP_HOST, SMTP_USER, SMTP_PASSWORD
                        A mail account, such as Gmail with an app password. Used when there's no Brevo key.
"""

import json
import re
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage

from creditcoach import config

BREVO_URL = "https://api.brevo.com/v3/smtp/email"
ADDRESS = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
BODY = """Your CreditCoach login

User ID:  {username}
Password: {password}

Keep this message. CreditCoach stores only a scrambled copy of your password, so it can't show it again or reset
it. If you lose it, you'll need to sign up again as a new user.

We have not kept your email address.
"""


def configured() -> bool:
    """Whether a way to send mail is set in ``.env``: a Brevo key and a sender, or a mail account."""
    return bool(config.BREVO_API_KEY and sender()) or bool(config.SMTP_HOST and config.SMTP_USER and config.SMTP_PASSWORD)


def sender() -> str:
    return config.SMTP_FROM or config.SMTP_USER


def valid(address: str) -> bool:
    """A loose check that ``address`` looks like one email address."""
    return bool(ADDRESS.fullmatch(address or "")) and len(address) <= 254


ADMIN_CHANGED = """The CreditCoach admin password was changed on {when}.

New password: {password}

Sign in at {url}/admin/

If you didn't make this change, reset the password from the admin sign-in page straight away.
"""
ADMIN_RESET = """Someone asked to reset the CreditCoach admin password.

Open this link to set a new one. It works once, for 30 minutes:
{link}

If you didn't ask for this, ignore this email: the password stays as it is.
"""


def why(exc: Exception) -> str:
    """What went wrong with a send, safe to log: the error's type, and Brevo's HTTP status if it answered (401 a bad
    key, 400 often a sender not confirmed in Brevo). Never the message, address or Brevo's own words."""
    status = getattr(exc, "code", None)
    return f"{type(exc).__name__} {status}" if isinstance(status, int) else type(exc).__name__


def send_login(address: str, username: str, password: str) -> None:
    """Send the login to ``address``.

    Raises:
        RuntimeError: No mail account is configured.
        smtplib.SMTPException, OSError: The mail server refused the message or couldn't be reached.
    """
    _send(address, "Your CreditCoach login", BODY.format(username=username, password=password))


def send_admin_password(password: str, when: str) -> None:
    """Email the new admin password to the admin address (``config.ADMIN_EMAIL``), never anywhere else. Raises as
    ``send_login`` does."""
    _send(config.ADMIN_EMAIL, "Your CreditCoach admin password was changed",
          ADMIN_CHANGED.format(when=when, password=password, url=config.PUBLIC_URL))


def send_admin_reset(link: str) -> None:
    """Email a one-time reset link to the admin address. Raises as ``send_login`` does."""
    _send(config.ADMIN_EMAIL, "Reset your CreditCoach admin password", ADMIN_RESET.format(link=link))


def _send(address: str, subject: str, body: str) -> None:
    if not configured():
        raise RuntimeError("no way to send mail is configured (BREVO_API_KEY, or SMTP_HOST, SMTP_USER, SMTP_PASSWORD)")
    if config.BREVO_API_KEY:
        _send_brevo(address, subject, body)
        return
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender()
    message["To"] = address
    message.set_content(body)
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as smtp:
        smtp.starttls()
        smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
        smtp.send_message(message)


def _send_brevo(address: str, subject: str, body: str) -> None:
    """Send through Brevo's email API. Raises ``OSError`` (``urllib.error.HTTPError``, with Brevo's reason) when Brevo
    refuses the message or can't be reached."""
    payload = {"sender": {"name": "CreditCoach", "email": sender()}, "to": [{"email": address}],
               "subject": subject, "textContent": body}
    request = urllib.request.Request(BREVO_URL, data=json.dumps(payload).encode(), method="POST", headers={
        "api-key": config.BREVO_API_KEY, "content-type": "application/json", "accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=20):
            pass
    except urllib.error.HTTPError as exc:
        reason = exc.read().decode(errors="replace")[:300]
        raise urllib.error.HTTPError(exc.url, exc.code, f"Brevo refused the message: {reason}", exc.headers,
                                     None) from None  # its reason may name the address: kept off the log (``why``)
