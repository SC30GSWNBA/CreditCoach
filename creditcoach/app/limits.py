"""The weekly question allowance: a signed-up user may ask ``config.WEEKLY_QUESTIONS`` (5) questions a week.

Every answer costs model calls, so people who sign up in the app get a fixed number of questions per week. The
week is the user's own: it starts with their first question and ends 7 days later, when the count starts again
with their next question. The 15 team logins (``auth.is_team``) have no limit.

A question is counted before it is answered (``take``), so two questions sent at once can't both slip past the
limit, and handed back (``give_back``) if the answer service fails. A question answered from the cache counts too.
Only real questions reach ``take``: empty messages are turned away earlier.

The counts live in Neon (``app_usage``, created by ``creditcoach.signup.store``): one row per user with the start of
their current week and how many questions they've asked in it.

Example:
    >>> grant = limits.take("USR-016")
    >>> grant.ok, grant.left
    (True, 4)
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from creditcoach import auth, config

WEEK = timedelta(days=7)
UNAVAILABLE = ("Sorry, I couldn't check your weekly questions just now, so I haven't answered. Please try again in "
               "a moment. This one hasn't been counted.")

# Count one question if the user has any left; a week that has ended starts again at 1. No row back = none left.
TAKE = """
INSERT INTO app_usage AS u (user_id, week_start, asked) VALUES (%(user_id)s, now(), 1)
ON CONFLICT (user_id) DO UPDATE SET
    week_start = CASE WHEN u.week_start + interval '7 days' <= now() THEN now() ELSE u.week_start END,
    asked      = CASE WHEN u.week_start + interval '7 days' <= now() THEN 1 ELSE u.asked + 1 END
WHERE u.week_start + interval '7 days' <= now() OR u.asked < %(limit)s
RETURNING week_start, asked
"""


@dataclass
class Grant:
    """The outcome of asking for one question.

    Attributes:
        ok: Whether the question may be answered (it has been counted if so).
        left: Questions left in the user's week after this one.
        resets: When the user's week ends and the count starts again.
    """

    ok: bool
    left: int
    resets: datetime


def applies(username: str | None) -> bool:
    """Whether ``username`` has a weekly limit: sign-up logins do, the team logins and unknown names don't."""
    return bool(username) and not auth.is_team(username) and username in auth.signup_logins()


def take(user_id: str) -> Grant:
    """Count one question for ``user_id`` if they have any left this week.

    Raises:
        Exception: Neon couldn't be reached. The caller must not answer, since nothing was counted.
    """
    from creditcoach.signup import store

    with store.connection() as conn:
        row = conn.execute(TAKE, {"user_id": user_id, "limit": config.WEEKLY_QUESTIONS}).fetchone()
        if row:
            return Grant(True, max(config.WEEKLY_QUESTIONS - row[1], 0), row[0] + WEEK)
        week_start = conn.execute("SELECT week_start FROM app_usage WHERE user_id = %s", (user_id,)).fetchone()[0]
    return Grant(False, 0, week_start + WEEK)


def give_back(user_id: str) -> None:
    """Uncount one question, after the answer service failed."""
    from creditcoach.signup import store

    with store.connection() as conn:
        conn.execute("UPDATE app_usage SET asked = greatest(asked - 1, 0) WHERE user_id = %s", (user_id,))


def when(moment: datetime) -> str:
    """``moment`` in the server's local time, e.g. ``Sun 18 Oct, 12:18 PM IST``."""
    return moment.astimezone().strftime("%a %d %b, %I:%M %p %Z").strip()


def used_up(grant: Grant) -> str:
    """The chat message for a user with no questions left this week."""
    n = config.WEEKLY_QUESTIONS
    return (f"You've used all {n} questions for this week. Your next {n} unlock on **{when(grant.resets)}**. "
            "Until then the **My credit** tab still shows your score story and accounts.")


def footer(grant: Grant) -> str:
    """The small line under an answer: how many questions are left and when the week resets."""
    return (f"\n\n<sub>Questions left this week: **{grant.left} of {config.WEEKLY_QUESTIONS}** · "
            f"resets {when(grant.resets)}</sub>")
