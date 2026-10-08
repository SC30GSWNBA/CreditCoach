"""Shared pieces for the CreditCoach tools: data loading, the user check, and the error envelope.

Both tools (``get_score_history``, Task 13; ``get_account_summary``, Task 14) follow ``docs/tools.md`` §1 and §4:
they read only the requested user's rows, return ``{"ok": true, ...}`` on success, and return the same error
envelope on failure instead of raising, so the agent (and, from Task 15, the MCP host) can read the error code.

Error codes raised here:
    UNKNOWN_USER      ``user_id`` is empty, malformed, or not in the dataset's users.
    DATA_UNAVAILABLE  The dataset can't be read (a file, or Neon; see ``creditcoach.dataset``). Retryable.

``USER_MISMATCH`` (the model asked for a user other than the signed-in one) and the 5-second timeout are
enforced by the MCP host in Task 15, not by the tools.
"""

import re
from functools import lru_cache

import pandas as pd

from creditcoach import dataset

USER_ID = re.compile(r"USR-\d{3}")
NO_CREDIT_FILE_NOTE = ("This user has no credit file yet: no credit accounts and no credit score. "
                       "Don't state or estimate a score.")


class ToolFailure(Exception):
    """Raised inside a tool to stop and return an error envelope (see ``error``)."""

    def __init__(self, code: str, message: str, retryable: bool = False, **details):
        super().__init__(message)
        self.envelope = error(code, message, retryable, **details)


def error(code: str, message: str, retryable: bool = False, **details) -> dict:
    """Build the shared error envelope from ``docs/tools.md`` §4."""
    return {"ok": False, "error": {"code": code, "message": message, "retryable": retryable, "details": details}}


@lru_cache(maxsize=1)
def tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Read users, accounts and score history once per process, from ``data/`` or Neon (``creditcoach.dataset``).

    Raises:
        ToolFailure: ``DATA_UNAVAILABLE`` if the dataset can't be read. Nothing is cached in that case, so a
            later call can succeed once the file (or Neon) is back.
    """
    try:
        return dataset.load()
    except dataset.DatasetError as exc:
        raise ToolFailure("DATA_UNAVAILABLE", f"Couldn't read the dataset: {exc}.", retryable=True) from exc


def as_of() -> str:
    """The dataset's latest month (``YYYY-MM-01``). "Now" for both tools (``docs/tools.md`` §1, rule 5)."""
    return str(tables()[2].date.max())[:10]


def check_user(user_id) -> str:
    """Return ``user_id`` if it names a user in the dataset.

    Raises:
        ToolFailure: ``UNKNOWN_USER`` if it is empty, malformed, or not in the dataset's users.
    """
    if not isinstance(user_id, str) or not USER_ID.fullmatch(user_id) or user_id not in set(tables()[0].user_id):
        raise ToolFailure("UNKNOWN_USER", f"No user with id {user_id}.", user_id=user_id)
    return user_id


def only_user(rows: pd.DataFrame, user_id: str) -> pd.DataFrame:
    """Return the rows for ``user_id``, checking again that no other user's row slipped through."""
    mine = rows[rows.user_id == user_id]
    if set(mine.user_id) - {user_id}:
        raise RuntimeError(f"Data for another user was selected while loading {user_id}")
    return mine
