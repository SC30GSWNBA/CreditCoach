"""Task 14: tests for ``get_account_summary`` against ``docs/tools.md`` §3 and the §5 test cases (T9-T15).

Expected figures come from ``data/accounts.csv``. If the dataset is regenerated, re-check them.

Run:
    uv run pytest tests/test_account_summary.py -v
"""

import json
import re
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd
import pytest

from creditcoach import config
from creditcoach.tools import common
from creditcoach.tools.account_summary import get_account_summary, ratio

SPEC = (config.ROOT / "docs" / "tools.md").read_text(encoding="utf-8")
SPEC_SECTION = SPEC.split("## 3. `get_account_summary")[1].split("## 4.")[0]
SPEC_EXAMPLES = [json.loads(b) for b in re.findall(r"```json\n(.*?)```", SPEC_SECTION, re.S) if '"ok":' in b]


def by_id(result):
    """Accounts keyed by account id."""
    return {a["account_id"]: a for a in result["accounts"]}


# ---- Spec test cases (docs/tools.md §5) ----

def test_t9_known_user():
    r = get_account_summary("USR-001")
    assert r["ok"] and r["has_credit_file"] and r["as_of"] == "2026-09-01" and "note" not in r
    assert list(by_id(r)) == ["ACC-01", "ACC-02", "ACC-03", "ACC-04", "ACC-05"]
    acc01 = by_id(r)["ACC-01"]
    assert (acc01["balance_inr"], acc01["credit_limit_inr"], acc01["utilization_ratio"]) == (59000, 75000, 0.787)
    assert r["totals"] == {"revolving_balance_inr": 74750, "revolving_limit_inr": 200000,
                           "overall_utilization_ratio": 0.374, "installment_balance_inr": 725000,
                           "total_balance_inr": 799750, "revolving_count": 3, "installment_count": 2}


def test_t10_two_cards():
    r = get_account_summary("USR-013")
    assert [a["utilization_ratio"] for a in r["accounts"]] == [0.089, 0.089]
    assert (r["totals"]["revolving_balance_inr"], r["totals"]["revolving_limit_inr"]) == (59200, 665000)
    assert r["totals"]["overall_utilization_ratio"] == 0.089


def test_t11_loan_only_has_no_ratio():
    r = get_account_summary("USR-005")
    assert r["has_credit_file"] and r["totals"]["revolving_count"] == 0
    assert r["totals"]["overall_utilization_ratio"] is None  # never 0
    assert "no credit card" in r["note"]


def test_t12_high_risk_product():
    r = get_account_summary("USR-012")
    assert [a["account_id"] for a in r["accounts"] if a["high_risk_product"]] == ["ACC-23"]
    assert by_id(r)["ACC-23"]["type"] == "Instant Loan App" and by_id(r)["ACC-23"]["category"] == "installment"
    assert r["totals"]["overall_utilization_ratio"] == 0.831 and r["totals"]["total_balance_inr"] == 4237100


def test_t13_no_credit_file_is_not_an_error():
    r = get_account_summary("USR-007")
    assert r["ok"] is True and r["has_credit_file"] is False and r["accounts"] == []
    assert r["totals"]["overall_utilization_ratio"] is None and r["totals"]["total_balance_inr"] == 0
    assert "no credit file" in r["note"]


def test_t14_unknown_user():
    assert get_account_summary("USR-999") == {"ok": False, "error": {
        "code": "UNKNOWN_USER", "message": "No user with id USR-999.", "retryable": False,
        "details": {"user_id": "USR-999"}}}


def test_t15_only_the_requested_users_accounts():
    csv = pd.read_csv(config.DATA_DIR / "accounts.csv")
    for uid in common.tables()[0].user_id:
        r = get_account_summary(uid)
        assert r["ok"] and r["user_id"] == uid
        assert set(by_id(r)) == set(csv[csv.user_id == uid].account_id)


# ---- The spec's examples stay true ----

@pytest.mark.parametrize("example", SPEC_EXAMPLES, ids=lambda e: e.get("user_id") or e["error"]["details"]["user_id"])
def test_spec_examples_match_the_tool(example):
    """Every complete JSON example in docs/tools.md §3 is exactly what the tool returns."""
    uid = example.get("user_id") or example["error"]["details"]["user_id"]
    assert get_account_summary(uid) == example


def test_spec_examples_were_found():
    assert len(SPEC_EXAMPLES) == 4  # USR-001, USR-005, USR-007 and the USR-999 error


# ---- Arithmetic and rules, for every user ----

def test_every_figure_matches_the_csv():
    """Balances and limits come from the CSV, ratios are balance / limit (3 places, half-up), totals are sums."""
    csv = pd.read_csv(config.DATA_DIR / "accounts.csv")
    for uid in common.tables()[0].user_id:
        r = get_account_summary(uid)
        cards = [a for a in r["accounts"] if a["category"] == "revolving"]
        loans = [a for a in r["accounts"] if a["category"] == "installment"]
        for a in r["accounts"]:
            row = csv[csv.account_id == a["account_id"]].iloc[0]
            assert a["balance_inr"] == row.balance_inr and a["type"] == row.account_type
            assert a["category"] == ("revolving" if row.account_type == "Credit Card" else "installment")
            assert a["high_risk_product"] == (row.account_type == "Instant Loan App")
        for a in cards:
            exact = Decimal(a["balance_inr"]) / Decimal(a["credit_limit_inr"])
            assert a["utilization_ratio"] == float(exact.quantize(Decimal("0.001"), ROUND_HALF_UP))
        for a in loans:
            assert a["credit_limit_inr"] is None and a["utilization_ratio"] is None
        t = r["totals"]
        assert t["revolving_balance_inr"] == sum(a["balance_inr"] for a in cards)
        assert t["revolving_limit_inr"] == sum(a["credit_limit_inr"] for a in cards)
        assert t["installment_balance_inr"] == sum(a["balance_inr"] for a in loans)
        assert t["total_balance_inr"] == t["revolving_balance_inr"] + t["installment_balance_inr"]
        assert (t["revolving_count"], t["installment_count"]) == (len(cards), len(loans))
        assert (t["overall_utilization_ratio"] is None) == (not cards)


def test_ratio_is_computed_not_read_from_the_csv():
    # The CSV stores 0.79 for ACC-01; the tool computes 59000 / 75000 = 0.787.
    assert by_id(get_account_summary("USR-001"))["ACC-01"]["utilization_ratio"] == 0.787


@pytest.mark.parametrize("balance, limit, expected", [
    (74750, 200000, 0.374),   # 0.37375 -> half-up
    (9, 2000, 0.005),         # 0.0045: float round() gives 0.004, half-up gives 0.005
    (0, 50000, 0.0),
    (50000, 50000, 1.0),
    (60000, 50000, 1.2),      # over the limit stays above 1, never capped
])
def test_ratio_rounding(balance, limit, expected):
    assert ratio(balance, limit) == expected


def test_accounts_are_in_numeric_id_order(monkeypatch):
    """Rows come back in account-number order even if the file isn't sorted, and ACC-100 sorts after ACC-99."""
    users, _, scores = common.tables()
    rows = pd.DataFrame([
        {"account_id": "ACC-100", "user_id": "USR-001", "account_type": "Credit Card", "balance_inr": 100,
         "credit_limit_inr": 1000.0, "utilization_ratio": 0.1},
        {"account_id": "ACC-99", "user_id": "USR-001", "account_type": "Home Loan", "balance_inr": 500,
         "credit_limit_inr": float("nan"), "utilization_ratio": float("nan")},
        {"account_id": "ACC-07", "user_id": "USR-001", "account_type": "Credit Card", "balance_inr": 50,
         "credit_limit_inr": 1000.0, "utilization_ratio": 0.05},
    ])
    monkeypatch.setattr("creditcoach.tools.account_summary.tables", lambda: (users, rows, scores))
    assert [a["account_id"] for a in get_account_summary("USR-001")["accounts"]] == ["ACC-07", "ACC-99", "ACC-100"]


def test_new_interview_users_are_served():
    r = get_account_summary("USR-014")
    assert [a["type"] for a in r["accounts"]] == ["Credit Card", "Home Loan"]
    assert r["totals"]["overall_utilization_ratio"] == 0.132


@pytest.mark.parametrize("user_id", ["usr-001", "", None, "USR-001 ", "Aravind", "USR-1"])
def test_unknown_user_forms(user_id):
    r = get_account_summary(user_id)
    assert r["error"]["code"] == "UNKNOWN_USER" and "accounts" not in r


def test_missing_data_file_is_data_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    common.tables.cache_clear()
    try:
        r = get_account_summary("USR-001")
        assert r["error"]["code"] == "DATA_UNAVAILABLE" and r["error"]["retryable"] is True
    finally:
        common.tables.cache_clear()  # later tests read the real files again
