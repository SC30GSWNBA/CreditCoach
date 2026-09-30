# Task 13 Evidence: Score-History Tool

*2026-09-30 · Code: `creditcoach/tools/score_history.py`, `creditcoach/tools/common.py` · Tests: `tests/test_score_history.py` · Script: `uv run python scripts/task13_score_history_test.py`*

**Definition of Done:** returns correct score data points and factor changes for a known period, and a clear error for an invalid one. The tool follows the spec in [docs/tools.md](../../tools.md) §2.

**Result: ✅ PASS** (6/6 logged cases correct; pytest passed)

## Summary

| # | Case | Call | Expected | Result |
|---|---|---|---|---|
| 1 | Known period: "What happened over the last two months?" (requirements.md §4 #7) | `get_score_history("USR-001", "last_2_months")` | Aug 670 (−20, utilization spike) and Sep 650 (−20, hard inquiry + utilization spike); 690 → 650 is −40, matching `data/score_history.csv` | ✅ |
| 2 | Known period: "What was my score in March?" (§4 #22) | `get_score_history("USR-001", "2026-03")` | Mar 2026: 678, +5 from 673, on-time payments | ✅ |
| 3 | Invalid period: wording the tool doesn't accept | `get_score_history("USR-001", "last quarter")` | Clear `INVALID_PERIOD` error that lists the accepted forms, and no partial data | ✅ |
| 4 | Invalid period: a month that doesn't exist | `get_score_history("USR-001", "2026-13")` | Clear `INVALID_PERIOD` error | ✅ |
| 5 | Valid period with no data: "What was my score in January 2025?" (§4 #46) | `get_score_history("USR-001", "2025-01")` | Clear `PERIOD_OUT_OF_RANGE` error naming the months on file, so the agent gives no estimate | ✅ |
| 6 | No credit file (§4 #14) | `get_score_history("USR-004", "latest")` | A normal result with no points and a note, not an error | ✅ |

## 1. Known period: "What happened over the last two months?" (requirements.md §4 #7)

`get_score_history("USR-001", "last_2_months")` returned:

```json
{
  "ok": true,
  "user_id": "USR-001",
  "as_of": "2026-09-01",
  "has_credit_file": true,
  "period": {
    "requested": "last_2_months",
    "start": "2026-08",
    "end": "2026-09",
    "clipped": false
  },
  "available": {
    "start": "2025-10",
    "end": "2026-09"
  },
  "points": [
    {
      "date": "2026-08-01",
      "score": 670,
      "change": -20,
      "factor_change": "Utilization spike"
    },
    {
      "date": "2026-09-01",
      "score": 650,
      "change": -20,
      "factor_change": "Hard inquiry + utilization spike"
    }
  ],
  "summary": {
    "start_score": 690,
    "end_score": 650,
    "net_change": -40,
    "lowest": {
      "date": "2026-09-01",
      "score": 650
    },
    "highest": {
      "date": "2026-08-01",
      "score": 670
    }
  }
}
```

## 2. Known period: "What was my score in March?" (§4 #22)

`get_score_history("USR-001", "2026-03")` returned:

```json
{
  "ok": true,
  "user_id": "USR-001",
  "as_of": "2026-09-01",
  "has_credit_file": true,
  "period": {
    "requested": "2026-03",
    "start": "2026-03",
    "end": "2026-03",
    "clipped": false
  },
  "available": {
    "start": "2025-10",
    "end": "2026-09"
  },
  "points": [
    {
      "date": "2026-03-01",
      "score": 678,
      "change": 5,
      "factor_change": "On-time payments"
    }
  ],
  "summary": {
    "start_score": 673,
    "end_score": 678,
    "net_change": 5,
    "lowest": {
      "date": "2026-03-01",
      "score": 678
    },
    "highest": {
      "date": "2026-03-01",
      "score": 678
    }
  }
}
```

## 3. Invalid period: wording the tool doesn't accept

`get_score_history("USR-001", "last quarter")` returned:

```json
{
  "ok": false,
  "error": {
    "code": "INVALID_PERIOD",
    "message": "Period 'last quarter' isn't valid. Use latest, last_N_months (N = 1-24), YYYY-MM, YYYY-MM:YYYY-MM or all.",
    "retryable": false,
    "details": {
      "requested": "last quarter"
    }
  }
}
```

## 4. Invalid period: a month that doesn't exist

`get_score_history("USR-001", "2026-13")` returned:

```json
{
  "ok": false,
  "error": {
    "code": "INVALID_PERIOD",
    "message": "Period '2026-13' isn't valid. Use latest, last_N_months (N = 1-24), YYYY-MM, YYYY-MM:YYYY-MM or all.",
    "retryable": false,
    "details": {
      "requested": "2026-13"
    }
  }
}
```

## 5. Valid period with no data: "What was my score in January 2025?" (§4 #46)

`get_score_history("USR-001", "2025-01")` returned:

```json
{
  "ok": false,
  "error": {
    "code": "PERIOD_OUT_OF_RANGE",
    "message": "No score history for 2025-01. History on file runs from 2025-10 to 2026-09.",
    "retryable": false,
    "details": {
      "requested": "2025-01",
      "available": {
        "start": "2025-10",
        "end": "2026-09"
      }
    }
  }
}
```

## 6. No credit file (§4 #14)

`get_score_history("USR-004", "latest")` returned:

```json
{
  "ok": true,
  "user_id": "USR-004",
  "as_of": "2026-09-01",
  "has_credit_file": false,
  "period": {
    "requested": "latest",
    "start": null,
    "end": null,
    "clipped": false
  },
  "available": null,
  "points": [],
  "summary": null,
  "note": "This user has no credit file yet: no credit accounts and no credit score. Don't state or estimate a score."
}
```

## Test log

`uv run pytest tests/test_score_history.py -v` covers the spec's test cases T1–T8 and T15 ([docs/tools.md](../../tools.md) §5), every invalid `period` form, clipping, unknown users, a missing data file, and a cross-check of every user's changes against the CSV.

```
============================= test session starts ==============================
collecting ... collected 42 items

tests/test_score_history.py::test_t1_latest_month PASSED                 [  2%]
tests/test_score_history.py::test_t2_last_two_months PASSED              [  4%]
tests/test_score_history.py::test_t3_single_month PASSED                 [  7%]
tests/test_score_history.py::test_t4_all_months PASSED                   [  9%]
tests/test_score_history.py::test_t5_window_longer_than_history_is_clipped PASSED [ 11%]
tests/test_score_history.py::test_t6_no_credit_file_is_not_an_error PASSED [ 14%]
tests/test_score_history.py::test_t7_period_out_of_range PASSED          [ 16%]
tests/test_score_history.py::test_t8_invalid_period PASSED               [ 19%]
tests/test_score_history.py::test_t15_only_the_requested_users_rows[latest] PASSED [ 21%]
tests/test_score_history.py::test_t15_only_the_requested_users_rows[all] PASSED [ 23%]
tests/test_score_history.py::test_t15_only_the_requested_users_rows[last_3_months] PASSED [ 26%]
tests/test_score_history.py::test_range_form_and_change_across_window_edge PASSED [ 28%]
tests/test_score_history.py::test_range_running_past_as_of_is_clipped PASSED [ 30%]
tests/test_score_history.py::test_range_entirely_before_history_is_out_of_range PASSED [ 33%]
tests/test_score_history.py::test_forms_are_case_and_space_insensitive[ LATEST ] PASSED [ 35%]
tests/test_score_history.py::test_forms_are_case_and_space_insensitive[Last_3_Months] PASSED [ 38%]
tests/test_score_history.py::test_forms_are_case_and_space_insensitive[last_1_month] PASSED [ 40%]
tests/test_score_history.py::test_requested_is_echoed_as_given PASSED    [ 42%]
tests/test_score_history.py::test_invalid_periods[2026-13] PASSED        [ 45%]
tests/test_score_history.py::test_invalid_periods[2026-00] PASSED        [ 47%]
tests/test_score_history.py::test_invalid_periods[26-03] PASSED          [ 50%]
tests/test_score_history.py::test_invalid_periods[last_0_months] PASSED  [ 52%]
tests/test_score_history.py::test_invalid_periods[last_25_months] PASSED [ 54%]
tests/test_score_history.py::test_invalid_periods[last_n_months] PASSED  [ 57%]
tests/test_score_history.py::test_invalid_periods[2026-09:2026-01] PASSED [ 59%]
tests/test_score_history.py::test_invalid_periods[] PASSED               [ 61%]
tests/test_score_history.py::test_invalid_periods[   ] PASSED            [ 64%]
tests/test_score_history.py::test_invalid_periods[None] PASSED           [ 66%]
tests/test_score_history.py::test_invalid_periods[202603] PASSED         [ 69%]
tests/test_score_history.py::test_invalid_periods[this month] PASSED     [ 71%]
tests/test_score_history.py::test_invalid_period_wins_over_no_credit_file PASSED [ 73%]
tests/test_score_history.py::test_no_credit_file_never_out_of_range PASSED [ 76%]
tests/test_score_history.py::test_unknown_user[USR-999] PASSED           [ 78%]
tests/test_score_history.py::test_unknown_user[usr-001] PASSED           [ 80%]
tests/test_score_history.py::test_unknown_user[] PASSED                  [ 83%]
tests/test_score_history.py::test_unknown_user[None] PASSED              [ 85%]
tests/test_score_history.py::test_unknown_user[USR-001 ] PASSED          [ 88%]
tests/test_score_history.py::test_unknown_user[Aravind] PASSED           [ 90%]
tests/test_score_history.py::test_new_interview_users_are_served PASSED  [ 92%]
tests/test_score_history.py::test_every_change_matches_the_data PASSED   [ 95%]
tests/test_score_history.py::test_missing_data_file_is_data_unavailable PASSED [ 97%]
tests/test_score_history.py::test_data_matches_csv_directly PASSED       [100%]

============================== 42 passed in 0.15s ==============================
```
