"""Task 14: ``get_account_summary(user_id)``, the signed-in user's accounts, utilization and totals.

Built to ``docs/tools.md`` §3. The tool does the arithmetic: each card's utilization, the overall ratio across
all cards, and the revolving, installment and total balances, so the model copies figures instead of
calculating them.

    Credit cards are ``revolving``: they have a limit and a utilization ratio.
    Every loan type is ``installment``: no limit, no ratio, and not part of utilization.
    ``Instant Loan App`` accounts (the dataset's payday-loan equivalent) are marked ``high_risk_product``.

Ratios are computed from the balance and limit, never read from the CSV's 2-place ``utilization_ratio``
column, and rounded half-up to 3 places (0.374 = 37.4%). A user with no accounts gets ``ok: true`` with
``has_credit_file: false``, never an error; a user with no card gets ``overall_utilization_ratio: null``, never 0.

Command line (prints the JSON result):
    uv run python -m creditcoach.tools.account_summary USR-001

Example:
    >>> from creditcoach.tools.account_summary import get_account_summary
    >>> r = get_account_summary("USR-001")
    >>> r["totals"]["overall_utilization_ratio"], r["totals"]["total_balance_inr"]
    (0.374, 799750)
    >>> get_account_summary("USR-999")["error"]["code"]
    'UNKNOWN_USER'
"""

import argparse
import json
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd

from creditcoach.tools.common import NO_CREDIT_FILE_NOTE, ToolFailure, as_of, check_user, only_user, tables

REVOLVING_TYPES = {"Credit Card"}
HIGH_RISK_TYPES = {"Instant Loan App"}
NO_CARD_NOTE = "This user has no credit card, so there is no utilization ratio. Don't report 0% or invent a limit."


def ratio(balance: int, limit: int) -> float:
    """``balance / limit`` rounded half-up to 3 places, computed exactly (no binary-float rounding drift)."""
    return float((Decimal(balance) / Decimal(limit)).quantize(Decimal("0.001"), ROUND_HALF_UP))


def _account(row) -> dict:
    """One ``accounts.csv`` row in the tool's output shape."""
    revolving = row.account_type in REVOLVING_TYPES
    limit = None if pd.isna(row.credit_limit_inr) else int(row.credit_limit_inr)
    if revolving and not limit:
        raise RuntimeError(f"{row.account_id}: a credit card needs a positive credit limit")
    return {"account_id": row.account_id,
            "type": row.account_type,
            "category": "revolving" if revolving else "installment",
            "balance_inr": int(row.balance_inr),
            "credit_limit_inr": limit if revolving else None,
            "utilization_ratio": ratio(int(row.balance_inr), limit) if revolving else None,
            "high_risk_product": row.account_type in HIGH_RISK_TYPES}


def get_account_summary(user_id: str) -> dict:
    """Return every account one user holds, with balances, limits, per-card utilization and totals.

    Args:
        user_id: Dataset id such as ``"USR-001"``. From Task 15 the MCP host fills it from the signed-in session.

    Returns:
        The success object from ``docs/tools.md`` §3 (``ok``, ``user_id``, ``as_of``, ``has_credit_file``,
        ``accounts``, ``totals``, and ``note`` when there is no credit file or no credit card), or the error
        envelope with code ``UNKNOWN_USER`` or ``DATA_UNAVAILABLE``. Never raises for these cases.
    """
    try:
        return _account_summary(user_id)
    except ToolFailure as failure:
        return failure.envelope


def _account_summary(user_id: str) -> dict:
    """``get_account_summary`` without the error wrapping; raises ``ToolFailure`` instead."""
    check_user(user_id)
    rows = only_user(tables()[1], user_id)
    rows = rows.assign(_n=rows.account_id.str.extract(r"(\d+)$", expand=False).astype(int)).sort_values("_n")
    accounts = [_account(r) for r in rows.itertuples()]

    cards = [a for a in accounts if a["category"] == "revolving"]
    loans = [a for a in accounts if a["category"] == "installment"]
    card_balance = sum(a["balance_inr"] for a in cards)
    card_limit = sum(a["credit_limit_inr"] for a in cards)
    loan_balance = sum(a["balance_inr"] for a in loans)
    result = {"ok": True, "user_id": user_id, "as_of": as_of(), "has_credit_file": bool(accounts),
              "accounts": accounts,
              "totals": {"revolving_balance_inr": card_balance,
                         "revolving_limit_inr": card_limit,
                         "overall_utilization_ratio": ratio(card_balance, card_limit) if cards else None,
                         "installment_balance_inr": loan_balance,
                         "total_balance_inr": card_balance + loan_balance,
                         "revolving_count": len(cards),
                         "installment_count": len(loans)}}
    if not accounts:
        result["note"] = NO_CREDIT_FILE_NOTE
    elif not cards:
        result["note"] = NO_CARD_NOTE
    return result


def main() -> None:
    """Print ``get_account_summary`` for a user as JSON."""
    parser = argparse.ArgumentParser(description="Show a user's accounts and utilization (Task 14 tool).")
    parser.add_argument("user_id", help='e.g. "USR-001"')
    args = parser.parse_args()
    print(json.dumps(get_account_summary(args.user_id), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
