# Task 13 Evidence: Score-History Tool

*2026-10-02 · Code: `creditcoach/tools/score_history.py`, `creditcoach/tools/common.py` · Tests: `tests/test_score_history.py` · Script: `uv run python scripts/task13_score_history_test.py`*

**Definition of Done:** returns correct score data points and factor changes for a known period, and a clear error for an invalid one. The tool follows the spec in [docs/tools.md](../../tools.md) §2.

**Result: ✅ PASS** (6/6 logged cases correct; pytest passed; requirements.md figures all match)

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

## All requirements.md figures for this tool (75 checks across 26 queries)

Every figure the expected answers in requirements.md §3 and §4 rely on that comes from this tool, read from a live call. The same checks run in CI as `tests/test_golden_queries.py`.

**Result: ✅ 75/75 match.**

| Query | Call | Field | Expected | Tool returned | Match |
|---|---|---|---|---|---|
| §3 #1 | `get_score_history("USR-001", "latest")` | `points.0.score` | `650` | `650` | ✅ |
| §3 #1 | `get_score_history("USR-001", "latest")` | `points.0.change` | `-20` | `-20` | ✅ |
| §3 #1 | `get_score_history("USR-001", "latest")` | `points.0.factor_change` | `'Hard inquiry + utilization spike'` | `'Hard inquiry + utilization spike'` | ✅ |
| §3 #3 | `get_score_history("USR-001", "latest")` | `points.0.score` | `650` | `650` | ✅ |
| §4 #7 | `get_score_history("USR-001", "2026-07")` | `points.0.score` | `690` | `690` | ✅ |
| §4 #7 | `get_score_history("USR-001", "2026-08")` | `points.0.score` | `670` | `670` | ✅ |
| §4 #7 | `get_score_history("USR-001", "2026-08")` | `points.0.change` | `-20` | `-20` | ✅ |
| §4 #7 | `get_score_history("USR-001", "2026-08")` | `points.0.factor_change` | `'Utilization spike'` | `'Utilization spike'` | ✅ |
| §4 #7 | `get_score_history("USR-001", "2026-09")` | `points.0.change` | `-20` | `-20` | ✅ |
| §4 #7 | `get_score_history("USR-001", "2026-09")` | `points.0.factor_change` | `'Hard inquiry + utilization spike'` | `'Hard inquiry + utilization spike'` | ✅ |
| §4 #8 | `get_score_history("USR-001", "2026-05")` | `points.0.score` | `676` | `676` | ✅ |
| §4 #8 | `get_score_history("USR-001", "2026-05")` | `points.0.change` | `-6` | `-6` | ✅ |
| §4 #8 | `get_score_history("USR-001", "2026-05")` | `points.0.factor_change` | `'Hard inquiry (new card)'` | `'Hard inquiry (new card)'` | ✅ |
| §4 #8 | `get_score_history("USR-001", "2026-09")` | `points.0.factor_change` | `'Hard inquiry + utilization spike'` | `'Hard inquiry + utilization spike'` | ✅ |
| §4 #9 | `get_score_history("USR-003", "2026-07")` | `points.0.score` | `772` | `772` | ✅ |
| §4 #9 | `get_score_history("USR-003", "2026-08")` | `points.0.score` | `763` | `763` | ✅ |
| §4 #9 | `get_score_history("USR-003", "2026-08")` | `points.0.change` | `-9` | `-9` | ✅ |
| §4 #9 | `get_score_history("USR-003", "2026-08")` | `points.0.factor_change` | `'Hard inquiry'` | `'Hard inquiry'` | ✅ |
| §4 #9 | `get_score_history("USR-003", "2026-09")` | `points.0.score` | `761` | `761` | ✅ |
| §4 #9 | `get_score_history("USR-003", "2026-09")` | `points.0.change` | `-2` | `-2` | ✅ |
| §4 #9 | `get_score_history("USR-003", "2026-09")` | `points.0.factor_change` | `'Hard inquiry'` | `'Hard inquiry'` | ✅ |
| §4 #9 | `get_score_history("USR-003", "all")` | `points.*.factor_change` | `"no item equals 'Late payment (30+ days)'"` | `'12 items, none matching'` | ✅ |
| §4 #10 | `get_score_history("USR-011", "2026-06")` | `points.0.score` | `728` | `728` | ✅ |
| §4 #10 | `get_score_history("USR-011", "2026-07")` | `points.0.score` | `724` | `724` | ✅ |
| §4 #10 | `get_score_history("USR-011", "2026-07")` | `points.0.change` | `-4` | `-4` | ✅ |
| §4 #10 | `get_score_history("USR-011", "2026-07")` | `points.0.factor_change` | `'Utilization increase'` | `'Utilization increase'` | ✅ |
| §4 #10 | `get_score_history("USR-011", "2026-08")` | `points.0.score` | `691` | `691` | ✅ |
| §4 #10 | `get_score_history("USR-011", "2026-08")` | `points.0.change` | `-33` | `-33` | ✅ |
| §4 #10 | `get_score_history("USR-011", "2026-08")` | `points.0.factor_change` | `'Utilization spike'` | `'Utilization spike'` | ✅ |
| §4 #11 | `get_score_history("USR-009", "2026-03")` | `points.0.score` | `811` | `811` | ✅ |
| §4 #11 | `get_score_history("USR-009", "2026-04")` | `points.0.score` | `729` | `729` | ✅ |
| §4 #11 | `get_score_history("USR-009", "2026-04")` | `points.0.change` | `-82` | `-82` | ✅ |
| §4 #11 | `get_score_history("USR-009", "2026-04")` | `points.0.factor_change` | `'Late payment (30+ days)'` | `'Late payment (30+ days)'` | ✅ |
| §4 #11 | `get_score_history("USR-009", "2026-05:2026-09")` | `points.*.factor_change` | `"no item equals 'Late payment (30+ days)'"` | `'5 items, none matching'` | ✅ |
| §4 #11 | `get_score_history("USR-009", "latest")` | `points.0.score` | `760` | `760` | ✅ |
| §4 #12 | `get_score_history("USR-012", "all")` | `summary.start_score` | `746` | `746` | ✅ |
| §4 #12 | `get_score_history("USR-012", "all")` | `summary.end_score` | `684` | `684` | ✅ |
| §4 #12 | `get_score_history("USR-012", "all")` | `summary.net_change` | `-62` | `-62` | ✅ |
| §4 #12 | `get_score_history("USR-012", "2026-03")` | `points.0.factor_change` | `'Hard inquiry'` | `'Hard inquiry'` | ✅ |
| §4 #12 | `get_score_history("USR-012", "2026-08")` | `points.0.score` | `703` | `703` | ✅ |
| §4 #12 | `get_score_history("USR-012", "latest")` | `points.0.change` | `-19` | `-19` | ✅ |
| §4 #13 | `get_score_history("USR-002", "latest")` | `points.0.score` | `837` | `837` | ✅ |
| §4 #13 | `get_score_history("USR-002", "latest")` | `points.0.change` | `4` | `4` | ✅ |
| §4 #13 | `get_score_history("USR-002", "latest")` | `points.0.factor_change` | `'On-time payments'` | `'On-time payments'` | ✅ |
| §4 #13 | `get_score_history("USR-002", "2026-08")` | `points.0.change` | `-2` | `-2` | ✅ |
| §4 #14 | `get_score_history("USR-004", "latest")` | `has_credit_file` | `False` | `False` | ✅ |
| §4 #14 | `get_score_history("USR-004", "latest")` | `points` | `[]` | `[]` | ✅ |
| §4 #20 | `get_score_history("USR-007", "latest")` | `has_credit_file` | `False` | `False` | ✅ |
| §4 #22 | `get_score_history("USR-001", "2026-03")` | `points.0.score` | `678` | `678` | ✅ |
| §4 #22 | `get_score_history("USR-001", "2026-03")` | `points.0.change` | `5` | `5` | ✅ |
| §4 #22 | `get_score_history("USR-001", "2026-03")` | `points.0.factor_change` | `'On-time payments'` | `'On-time payments'` | ✅ |
| §4 #23 | `get_score_history("USR-003", "2026-08")` | `points.0.factor_change` | `'Hard inquiry'` | `'Hard inquiry'` | ✅ |
| §4 #23 | `get_score_history("USR-003", "2026-09")` | `points.0.factor_change` | `'Hard inquiry'` | `'Hard inquiry'` | ✅ |
| §4 #23 | `get_score_history("USR-003", "all")` | `points.*.factor_change` | `"no item equals 'Late payment (30+ days)'"` | `'12 items, none matching'` | ✅ |
| §4 #24 | `get_score_history("USR-013", "latest")` | `points.0.score` | `841` | `841` | ✅ |
| §4 #24 | `get_score_history("USR-013", "all")` | `points.*.factor_change` | `"no item equals 'Late payment (30+ days)'"` | `'12 items, none matching'` | ✅ |
| §4 #25 | `get_score_history("USR-001", "latest")` | `points.0.score` | `650` | `650` | ✅ |
| §4 #26 | `get_score_history("USR-008", "latest")` | `points.0.score` | `710` | `710` | ✅ |
| §4 #26 | `get_score_history("USR-008", "2025-10")` | `points.0.score` | `657` | `657` | ✅ |
| §4 #27 | `get_score_history("USR-006", "latest")` | `points.0.score` | `802` | `802` | ✅ |
| §4 #28 | `get_score_history("USR-010", "latest")` | `points.0.score` | `795` | `795` | ✅ |
| §4 #33 | `get_score_history("USR-001", "2026-05")` | `points.0.factor_change` | `'Hard inquiry (new card)'` | `'Hard inquiry (new card)'` | ✅ |
| §4 #33 | `get_score_history("USR-001", "2026-09")` | `points.0.factor_change` | `'Hard inquiry + utilization spike'` | `'Hard inquiry + utilization spike'` | ✅ |
| §4 #34 | `get_score_history("USR-009", "2026-04")` | `points.0.score` | `729` | `729` | ✅ |
| §4 #34 | `get_score_history("USR-009", "latest")` | `points.0.score` | `760` | `760` | ✅ |
| §4 #36 | `get_score_history("USR-013", "latest")` | `points.0.score` | `841` | `841` | ✅ |
| §4 #37 | `get_score_history("USR-001", "latest")` | `points.0.score` | `650` | `650` | ✅ |
| §4 #41 | `get_score_history("USR-001", "2026-08")` | `points.0.factor_change` | `'Utilization spike'` | `'Utilization spike'` | ✅ |
| §4 #41 | `get_score_history("USR-001", "2026-09")` | `points.0.factor_change` | `'Hard inquiry + utilization spike'` | `'Hard inquiry + utilization spike'` | ✅ |
| §4 #42 | `get_score_history("USR-009", "latest")` | `points.0.score` | `760` | `760` | ✅ |
| §4 #42 | `get_score_history("USR-009", "2026-03")` | `points.0.score` | `811` | `811` | ✅ |
| §4 #46 | `get_score_history("USR-001", "2025-01")` | `error.code` | `'PERIOD_OUT_OF_RANGE'` | `'PERIOD_OUT_OF_RANGE'` | ✅ |
| §4 #46 | `get_score_history("USR-001", "2025-01")` | `error.details.available.start` | `'2025-10'` | `'2025-10'` | ✅ |
| §4 #46 | `get_score_history("USR-001", "2025-01")` | `error.details.available.end` | `'2026-09'` | `'2026-09'` | ✅ |
| §4 #49 | `get_score_history("USR-003", "latest")` | `points.0.score` | `761` | `761` | ✅ |

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

============================== 42 passed in 0.16s ==============================
```
