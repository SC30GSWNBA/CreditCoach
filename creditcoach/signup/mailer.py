"""Email a new login to the person who just signed up: the optional backup for the one-time password pop-up.

The message is sent once, straight after sign-up, with the User ID and password the pop-up shows. The address is
used for that one message and is not stored or logged. CreditCoach keeps only a hash of the password, so this
email (or the person's own copy) is the only record of it.

It needs a mail account in ``.env`` (``SMTP_HOST``, ``SMTP_USER``, ``SMTP_PASSWORD``; see ``.env.example``). Without
one, ``configured()`` is False and the pop-up leaves the email option out.
"""

import re
import smtplib
from email.message import EmailMessage

from creditcoach import config

ADDRESS = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
BODY = """Your CreditCoach login

User ID:  {username}
Password: {password}

Keep this message. CreditCoach stores only a scrambled copy of your password, so it can't show it again or reset
it. If you lose it, you'll need to sign up again as a new user.

We have not kept your email address.
"""


def configured() -> bool:
    """Whether a mail account is set in ``.env``."""
    return bool(config.SMTP_HOST and config.SMTP_USER and config.SMTP_PASSWORD)


def valid(address: str) -> bool:
    """A loose check that ``address`` looks like one email address."""
    return bool(ADDRESS.fullmatch(address or "")) and len(address) <= 254


def send_login(address: str, username: str, password: str) -> None:
    """Send the login to ``address``.

    Raises:
        RuntimeError: No mail account is configured.
        smtplib.SMTPException, OSError: The mail server refused the message or couldn't be reached.
    """
    if not configured():
        raise RuntimeError("no mail account is configured (SMTP_HOST, SMTP_USER, SMTP_PASSWORD)")
    message = EmailMessage()
    message["Subject"] = "Your CreditCoach login"
    message["From"] = config.SMTP_FROM or config.SMTP_USER
    message["To"] = address
    message.set_content(BODY.format(username=username, password=password))
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as smtp:
        smtp.starttls()
        smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
        smtp.send_message(message)
