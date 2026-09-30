# Task 14 Evidence: Account-Summary Tool

*2026-09-30 · Code: `creditcoach/tools/account_summary.py`, `creditcoach/tools/common.py` · Tests: `tests/test_account_summary.py` · Script: `uv run python scripts/task14_account_summary_test.py`*

**Definition of Done:** returns correct balances, limits and utilization ratio for a known user, and a clear error for an unknown one. The tool follows the spec in [docs/tools.md](../../tools.md) §3.

**How utilization is computed:** balance ÷ limit for each credit card, and total card balances ÷ total card limits overall, rounded half-up to 3 places (0.374 = 37.4%). Loans have no limit and don't count. The tool never reads the CSV's 2-place `utilization_ratio` column, so ACC-01 is 0.787, not 0.79.

**Result: ✅ PASS** (6/6 logged cases correct; pytest passed)

## Summary

| # | Case | Call | Expected | Result |
|---|---|---|---|---|
| 1 | Known user: "What's my current credit utilization ratio?" (requirements.md §3 #2, §4 #15, #17) | `get_account_summary("USR-001")` | Cards ACC-01 ₹59,000 ÷ ₹75,000 = 0.787, ACC-02 ₹11,000 ÷ ₹1,00,000 = 0.11, ACC-05 ₹4,750 ÷ ₹25,000 = 0.19; overall ₹74,750 ÷ ₹2,00,000 = 0.374; the two loans are left out of utilization; total debt ₹7,99,750 | ✅ |
| 2 | Known user with two cards: "What's my credit utilization?" (§4 #18) | `get_account_summary("USR-013")` | Both cards 0.089; overall ₹59,200 ÷ ₹6,65,000 = 0.089 | ✅ |
| 3 | Loan only, no credit card (§4 #19) | `get_account_summary("USR-005")` | Education loan ₹3,30,000; overall ratio `null` (not 0%) with a note saying why | ✅ |
| 4 | High-risk product: "Is my card usage too high?" (§4 #12, #21) | `get_account_summary("USR-012")` | Card ₹3,78,100 ÷ ₹4,55,000 = 0.831; the Instant Loan App (ACC-23) is marked `high_risk_product` | ✅ |
| 5 | Unknown user | `get_account_summary("USR-999")` | Clear `UNKNOWN_USER` error and no partial data | ✅ |
| 6 | No credit file (§4 #20) | `get_account_summary("USR-007")` | A normal result with no accounts and a note, not an error | ✅ |

## 1. Known user: "What's my current credit utilization ratio?" (requirements.md §3 #2, §4 #15, #17)

`get_account_summary("USR-001")` returned:

```json
{
  "ok": true,
  "user_id": "USR-001",
  "as_of": "2026-09-01",
  "has_credit_file": true,
  "accounts": [
    {
      "account_id": "ACC-01",
      "type": "Credit Card",
      "category": "revolving",
      "balance_inr": 59000,
      "credit_limit_inr": 75000,
      "utilization_ratio": 0.787,
      "high_risk_product": false
    },
    {
      "account_id": "ACC-02",
      "type": "Credit Card",
      "category": "revolving",
      "balance_inr": 11000,
      "credit_limit_inr": 100000,
      "utilization_ratio": 0.11,
      "high_risk_product": false
    },
    {
      "account_id": "ACC-03",
      "type": "Education Loan",
      "category": "installment",
      "balance_inr": 420000,
      "credit_limit_inr": null,
      "utilization_ratio": null,
      "high_risk_product": false
    },
    {
      "account_id": "ACC-04",
      "type": "Auto Loan",
      "category": "installment",
      "balance_inr": 305000,
      "credit_limit_inr": null,
      "utilization_ratio": null,
      "high_risk_product": false
    },
    {
      "account_id": "ACC-05",
      "type": "Credit Card",
      "category": "revolving",
      "balance_inr": 4750,
      "credit_limit_inr": 25000,
      "utilization_ratio": 0.19,
      "high_risk_product": false
    }
  ],
  "totals": {
    "revolving_balance_inr": 74750,
    "revolving_limit_inr": 200000,
    "overall_utilization_ratio": 0.374,
    "installment_balance_inr": 725000,
    "total_balance_inr": 799750,
    "revolving_count": 3,
    "installment_count": 2
  }
}
```

## 2. Known user with two cards: "What's my credit utilization?" (§4 #18)

`get_account_summary("USR-013")` returned:

```json
{
  "ok": true,
  "user_id": "USR-013",
  "as_of": "2026-09-01",
  "has_credit_file": true,
  "accounts": [
    {
      "account_id": "ACC-24",
      "type": "Credit Card",
      "category": "revolving",
      "balance_inr": 28600,
      "credit_limit_inr": 320000,
      "utilization_ratio": 0.089,
      "high_risk_product": false
    },
    {
      "account_id": "ACC-25",
      "type": "Credit Card",
      "category": "revolving",
      "balance_inr": 30600,
      "credit_limit_inr": 345000,
      "utilization_ratio": 0.089,
      "high_risk_product": false
    }
  ],
  "totals": {
    "revolving_balance_inr": 59200,
    "revolving_limit_inr": 665000,
    "overall_utilization_ratio": 0.089,
    "installment_balance_inr": 0,
    "total_balance_inr": 59200,
    "revolving_count": 2,
    "installment_count": 0
  }
}
```

## 3. Loan only, no credit card (§4 #19)

`get_account_summary("USR-005")` returned:

```json
{
  "ok": true,
  "user_id": "USR-005",
  "as_of": "2026-09-01",
  "has_credit_file": true,
  "accounts": [
    {
      "account_id": "ACC-10",
      "type": "Education Loan",
      "category": "installment",
      "balance_inr": 330000,
      "credit_limit_inr": null,
      "utilization_ratio": null,
      "high_risk_product": false
    }
  ],
  "totals": {
    "revolving_balance_inr": 0,
    "revolving_limit_inr": 0,
    "overall_utilization_ratio": null,
    "installment_balance_inr": 330000,
    "total_balance_inr": 330000,
    "revolving_count": 0,
    "installment_count": 1
  },
  "note": "This user has no credit card, so there is no utilization ratio. Don't report 0% or invent a limit."
}
```

## 4. High-risk product: "Is my card usage too high?" (§4 #12, #21)

`get_account_summary("USR-012")` returned:

```json
{
  "ok": true,
  "user_id": "USR-012",
  "as_of": "2026-09-01",
  "has_credit_file": true,
  "accounts": [
    {
      "account_id": "ACC-20",
      "type": "Credit Card",
      "category": "revolving",
      "balance_inr": 378100,
      "credit_limit_inr": 455000,
      "utilization_ratio": 0.831,
      "high_risk_product": false
    },
    {
      "account_id": "ACC-21",
      "type": "Home Loan",
      "category": "installment",
      "balance_inr": 3410000,
      "credit_limit_inr": null,
      "utilization_ratio": null,
      "high_risk_product": false
    },
    {
      "account_id": "ACC-22",
      "type": "Personal Loan",
      "category": "installment",
      "balance_inr": 425000,
      "credit_limit_inr": null,
      "utilization_ratio": null,
      "high_risk_product": false
    },
    {
      "account_id": "ACC-23",
      "type": "Instant Loan App",
      "category": "installment",
      "balance_inr": 24000,
      "credit_limit_inr": null,
      "utilization_ratio": null,
      "high_risk_product": true
    }
  ],
  "totals": {
    "revolving_balance_inr": 378100,
    "revolving_limit_inr": 455000,
    "overall_utilization_ratio": 0.831,
    "installment_balance_inr": 3859000,
    "total_balance_inr": 4237100,
    "revolving_count": 1,
    "installment_count": 3
  }
}
```

## 5. Unknown user

`get_account_summary("USR-999")` returned:

```json
{
  "ok": false,
  "error": {
    "code": "UNKNOWN_USER",
    "message": "No user with id USR-999.",
    "retryable": false,
    "details": {
      "user_id": "USR-999"
    }
  }
}
```

## 6. No credit file (§4 #20)

`get_account_summary("USR-007")` returned:

```json
{
  "ok": true,
  "user_id": "USR-007",
  "as_of": "2026-09-01",
  "has_credit_file": false,
  "accounts": [],
  "totals": {
    "revolving_balance_inr": 0,
    "revolving_limit_inr": 0,
    "overall_utilization_ratio": null,
    "installment_balance_inr": 0,
    "total_balance_inr": 0,
    "revolving_count": 0,
    "installment_count": 0
  },
  "note": "This user has no credit file yet: no credit accounts and no credit score. Don't state or estimate a score."
}
```

## Test log

`uv run pytest tests/test_account_summary.py -v` covers the spec's test cases T9–T15 ([docs/tools.md](../../tools.md) §5), checks that every complete JSON example in the spec is exactly what the tool returns, recomputes every user's ratios and totals from the CSV, and covers rounding, account order, unknown users and a missing data file.

```
============================= test session starts ==============================
collecting ... collected 28 items

tests/test_account_summary.py::test_t9_known_user PASSED                 [  3%]
tests/test_account_summary.py::test_t10_two_cards PASSED                 [  7%]
tests/test_account_summary.py::test_t11_loan_only_has_no_ratio PASSED    [ 10%]
tests/test_account_summary.py::test_t12_high_risk_product PASSED         [ 14%]
tests/test_account_summary.py::test_t13_no_credit_file_is_not_an_error PASSED [ 17%]
tests/test_account_summary.py::test_t14_unknown_user PASSED              [ 21%]
tests/test_account_summary.py::test_t15_only_the_requested_users_accounts PASSED [ 25%]
tests/test_account_summary.py::test_spec_examples_match_the_tool[USR-001] PASSED [ 28%]
tests/test_account_summary.py::test_spec_examples_match_the_tool[USR-005] PASSED [ 32%]
tests/test_account_summary.py::test_spec_examples_match_the_tool[USR-007] PASSED [ 35%]
tests/test_account_summary.py::test_spec_examples_match_the_tool[USR-999] PASSED [ 39%]
tests/test_account_summary.py::test_spec_examples_were_found PASSED      [ 42%]
tests/test_account_summary.py::test_every_figure_matches_the_csv PASSED  [ 46%]
tests/test_account_summary.py::test_ratio_is_computed_not_read_from_the_csv PASSED [ 50%]
tests/test_account_summary.py::test_ratio_rounding[74750-200000-0.374] PASSED [ 53%]
tests/test_account_summary.py::test_ratio_rounding[9-2000-0.005] PASSED  [ 57%]
tests/test_account_summary.py::test_ratio_rounding[0-50000-0.0] PASSED   [ 60%]
tests/test_account_summary.py::test_ratio_rounding[50000-50000-1.0] PASSED [ 64%]
tests/test_account_summary.py::test_ratio_rounding[60000-50000-1.2] PASSED [ 67%]
tests/test_account_summary.py::test_accounts_are_in_numeric_id_order PASSED [ 71%]
tests/test_account_summary.py::test_new_interview_users_are_served PASSED [ 75%]
tests/test_account_summary.py::test_unknown_user_forms[usr-001] PASSED   [ 78%]
tests/test_account_summary.py::test_unknown_user_forms[] PASSED          [ 82%]
tests/test_account_summary.py::test_unknown_user_forms[None] PASSED      [ 85%]
tests/test_account_summary.py::test_unknown_user_forms[USR-001 ] PASSED  [ 89%]
tests/test_account_summary.py::test_unknown_user_forms[Aravind] PASSED   [ 92%]
tests/test_account_summary.py::test_unknown_user_forms[USR-1] PASSED     [ 96%]
tests/test_account_summary.py::test_missing_data_file_is_data_unavailable PASSED [100%]

============================== 28 passed in 0.15s ==============================
```
