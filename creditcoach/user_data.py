"""One user's own data from the synthetic dataset, and nothing else.

The chat UI signs each person in as one user (``creditcoach.auth``). Since Task 15 the pipeline uses this
module only for the user's interview profile (USER PROFILE in the model's context); scores and accounts reach
the model through the MCP tools in ``creditcoach.tools``. The app also uses it for the "Signed in as" name.
It returns rows for the requested ``user_id`` only, so another user's data never reaches the model.

The output uses the field names of the Week 2 tools (``get_score_history``, ``get_account_summary``), specified
in ``docs/tools.md``, which let Tasks 13-15 replace its score and account data with real tool calls. The
tools return more than this module: each month's score change, a period summary, account totals, and utilization
computed from balance / limit to 3 places (this module passes on the CSV's 2-place ratio).

Example:
    >>> from creditcoach.user_data import load_user_data
    >>> data = load_user_data("USR-001")
    >>> data["get_score_history"]["points"][-1]
    {'date': '2026-09-01', 'score': 650, 'factor_change': 'Hard inquiry + utilization spike'}
"""

from functools import lru_cache

import pandas as pd

from creditcoach import config

# Profile answers from users.csv that help explain a user's credit. Leaves out survey bookkeeping
# (source, age band, knowledge score) and fields with no bearing on credit coaching.
PROFILE_FIELDS = ["first_name", "age", "years_working", "credit_cards", "pays_card", "card_usage",
                  "late_payments_12m", "loans", "risky_product_exposure", "emergency_fund", "emi_pct", "goals_2yr"]


class UnknownUserError(KeyError):
    """Raised when a user id is not in ``data/users.csv``."""


@lru_cache(maxsize=1)
def _tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Read the three dataset files once per process: users, accounts, score history."""
    users = pd.read_csv(config.DATA_DIR / "users.csv", dtype=str, keep_default_na=False)
    accounts = pd.read_csv(config.DATA_DIR / "accounts.csv")
    scores = pd.read_csv(config.DATA_DIR / "score_history.csv")
    return users, accounts, scores


def user_ids() -> list[str]:
    """Return every user id in the dataset, in file order."""
    return _tables()[0]["user_id"].tolist()


def load_user_data(user_id: str) -> dict:
    """Return one user's profile, full score history and accounts, using the Week 2 tools' field names.

    Every row is filtered by ``user_id`` and checked again before it is returned, so the result can't
    contain another user's data even if a filter is later changed by mistake.

    Args:
        user_id: A dataset id such as ``"USR-001"``, taken from the signed-in session, never from user text.

    Returns:
        ``{"user_profile": {...}, "get_score_history": {...}, "get_account_summary": {...}}``. A user with no
        credit file has empty ``points`` and ``accounts`` and a note saying so.

    Raises:
        UnknownUserError: If ``user_id`` is not in the dataset.
    """
    users, accounts, scores = _tables()
    match = users[users.user_id == user_id]
    if len(match) != 1:
        raise UnknownUserError(user_id)
    profile = {k: v for k, v in match.iloc[0][PROFILE_FIELDS].items() if v}
    scores = scores[scores.user_id == user_id]
    accounts = accounts[accounts.user_id == user_id]
    if not (set(scores.user_id) | set(accounts.user_id)) <= {user_id}:
        raise RuntimeError(f"Data for another user was selected while loading {user_id}")

    data = {
        "user_profile": {"user_id": user_id, **profile},
        "get_score_history": {
            "user_id": user_id,
            "period": "all_available_months",
            "points": [{"date": str(r.date)[:10], "score": int(r.score), "factor_change": r.primary_factor_change}
                       for r in scores.itertuples()],
        },
        "get_account_summary": {
            "user_id": user_id,
            "accounts": [{"account_id": r.account_id,
                          "type": r.account_type,
                          "balance_inr": int(r.balance_inr),
                          "credit_limit_inr": None if pd.isna(r.credit_limit_inr) else int(r.credit_limit_inr),
                          "utilization_ratio": None if pd.isna(r.utilization_ratio) else float(r.utilization_ratio)}
                         for r in accounts.itertuples()],
        },
    }
    if scores.empty and accounts.empty:
        data["note"] = ("This user has no credit file yet: no credit accounts and no credit score. "
                        "Don't state or estimate a score.")
    return data
