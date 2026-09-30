"""Task 14: write the test log for the account-summary tool.

Definition of Done: the tool returns correct balances, limits and utilization ratio for a known user, and a clear
error for an unknown one. This script logs those cases (plus two cards, a loan-only file, a high-risk product
and a user with no credit file) with the tool's full output, checks each against the expected figures, and
appends the pytest run for the whole test file.

Writes:
    docs/evidence/week-2/task-14-account-summary-test.md

Run (no API key needed; results are deterministic):
    uv run python scripts/task14_account_summary_test.py
"""

import json
import subprocess
import sys
from datetime import date

from creditcoach import config
from creditcoach.tools.account_summary import get_account_summary

EVIDENCE = config.ROOT / "docs" / "evidence" / "week-2" / "task-14-account-summary-test.md"


def cards(r):
    """(account id, balance, limit, ratio) for each credit card."""
    return [(a["account_id"], a["balance_inr"], a["credit_limit_inr"], a["utilization_ratio"])
            for a in r["accounts"] if a["category"] == "revolving"]


# (title, user_id, check on the result, what the check means)
CASES = [
    ("Known user: \"What's my current credit utilization ratio?\" (requirements.md §3 #2, §4 #15, #17)", "USR-001",
     lambda r: cards(r) == [("ACC-01", 59000, 75000, 0.787), ("ACC-02", 11000, 100000, 0.11),
                            ("ACC-05", 4750, 25000, 0.19)]
     and r["totals"]["overall_utilization_ratio"] == 0.374 and r["totals"]["revolving_limit_inr"] == 200000
     and r["totals"]["total_balance_inr"] == 799750,
     "Cards ACC-01 ₹59,000 ÷ ₹75,000 = 0.787, ACC-02 ₹11,000 ÷ ₹1,00,000 = 0.11, ACC-05 ₹4,750 ÷ ₹25,000 = 0.19; "
     "overall ₹74,750 ÷ ₹2,00,000 = 0.374; the two loans are left out of utilization; total debt ₹7,99,750"),
    ("Known user with two cards: \"What's my credit utilization?\" (§4 #18)", "USR-013",
     lambda r: cards(r) == [("ACC-24", 28600, 320000, 0.089), ("ACC-25", 30600, 345000, 0.089)]
     and r["totals"]["overall_utilization_ratio"] == 0.089,
     "Both cards 0.089; overall ₹59,200 ÷ ₹6,65,000 = 0.089"),
    ("Loan only, no credit card (§4 #19)", "USR-005",
     lambda r: cards(r) == [] and r["totals"]["overall_utilization_ratio"] is None
     and r["totals"]["installment_balance_inr"] == 330000 and "no credit card" in r["note"],
     "Education loan ₹3,30,000; overall ratio `null` (not 0%) with a note saying why"),
    ("High-risk product: \"Is my card usage too high?\" (§4 #12, #21)", "USR-012",
     lambda r: cards(r) == [("ACC-20", 378100, 455000, 0.831)]
     and [a["account_id"] for a in r["accounts"] if a["high_risk_product"]] == ["ACC-23"],
     "Card ₹3,78,100 ÷ ₹4,55,000 = 0.831; the Instant Loan App (ACC-23) is marked `high_risk_product`"),
    ("Unknown user", "USR-999",
     lambda r: r["ok"] is False and r["error"]["code"] == "UNKNOWN_USER" and "accounts" not in r,
     "Clear `UNKNOWN_USER` error and no partial data"),
    ("No credit file (§4 #20)", "USR-007",
     lambda r: r["ok"] is True and r["has_credit_file"] is False and r["accounts"] == [],
     "A normal result with no accounts and a note, not an error"),
]


def main() -> None:
    """Run the logged cases and the pytest suite, then write the evidence file."""
    results = [(title, uid, get_account_summary(uid), check, meaning) for title, uid, check, meaning in CASES]
    passed = [check(r) for _, _, r, check, _ in results]
    test = subprocess.run([sys.executable, "-m", "pytest", "tests/test_account_summary.py", "-v", "--no-header",
                           "-p", "no:cacheprovider"], cwd=config.ROOT, capture_output=True, text=True)
    log = test.stdout.strip().replace(str(config.ROOT) + "/", "")
    ok = all(passed) and test.returncode == 0

    lines = [
        "# Task 14 Evidence: Account-Summary Tool",
        "",
        f"*{date.today().isoformat()} · Code: `creditcoach/tools/account_summary.py`, `creditcoach/tools/common.py` · "
        "Tests: `tests/test_account_summary.py` · Script: `uv run python scripts/task14_account_summary_test.py`*",
        "",
        "**Definition of Done:** returns correct balances, limits and utilization ratio for a known user, and a "
        "clear error for an unknown one. The tool follows the spec in [docs/tools.md](../../tools.md) §3.",
        "",
        "**How utilization is computed:** balance ÷ limit for each credit card, and total card balances ÷ total "
        "card limits overall, rounded half-up to 3 places (0.374 = 37.4%). Loans have no limit and don't count. "
        "The tool never reads the CSV's 2-place `utilization_ratio` column, so ACC-01 is 0.787, not 0.79.",
        "",
        f"**Result: {'✅ PASS' if ok else '❌ FAIL'}** ({sum(passed)}/{len(passed)} logged cases correct; "
        f"pytest {'passed' if test.returncode == 0 else 'FAILED'})",
        "",
        "## Summary",
        "",
        "| # | Case | Call | Expected | Result |",
        "|---|---|---|---|---|",
    ]
    for i, ((title, uid, _, _, meaning), good) in enumerate(zip(results, passed), 1):
        lines.append(f"| {i} | {title} | `get_account_summary(\"{uid}\")` | {meaning} | {'✅' if good else '❌'} |")
    for i, (title, uid, result, _, _) in enumerate(results, 1):
        lines += ["", f"## {i}. {title}", "", f"`get_account_summary(\"{uid}\")` returned:", "",
                  "```json", json.dumps(result, indent=2, ensure_ascii=False), "```"]
    lines += ["", "## Test log", "", "`uv run pytest tests/test_account_summary.py -v` covers the spec's test cases "
              "T9–T15 ([docs/tools.md](../../tools.md) §5), checks that every complete JSON example in the spec is "
              "exactly what the tool returns, recomputes every user's ratios and totals from the CSV, and covers "
              "rounding, account order, unknown users and a missing data file.",
              "", "```", log, "```", ""]
    EVIDENCE.write_text("\n".join(lines), encoding="utf-8")
    print(f"{'PASS' if ok else 'FAIL'}: wrote {EVIDENCE.relative_to(config.ROOT)}")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
