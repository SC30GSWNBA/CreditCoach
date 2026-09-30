"""Task 13: tests for ``get_score_history`` against ``docs/tools.md`` §2 and the §5 test cases (T1-T8, T15).

Expected figures come from ``data/score_history.csv`` (latest month Sep 2026). If the dataset is regenerated,
re-check them.

Run:
    uv run pytest tests/test_score_history.py -v
"""

import pandas as pd
import pytest

from creditcoach import config
from creditcoach.tools import common
from creditcoach.tools.score_history import get_score_history

AVAILABLE = {"start": "2025-10", "end": "2026-09"}


def points(result):
    """(date, score, change, factor) tuples, for compact comparisons."""
    return [(p["date"], p["score"], p["change"], p["factor_change"]) for p in result["points"]]


# ---- Spec test cases (docs/tools.md §5) ----

def test_t1_latest_month():
    r = get_score_history("USR-001", "latest")
    assert r["ok"] and r["has_credit_file"] and r["as_of"] == "2026-09-01"
    assert points(r) == [("2026-09-01", 650, -20, "Hard inquiry + utilization spike")]
    assert r["summary"]["start_score"] == 670 and r["summary"]["net_change"] == -20


def test_t2_last_two_months():
    r = get_score_history("USR-001", "last_2_months")
    assert points(r) == [("2026-08-01", 670, -20, "Utilization spike"),
                         ("2026-09-01", 650, -20, "Hard inquiry + utilization spike")]
    assert r["period"] == {"requested": "last_2_months", "start": "2026-08", "end": "2026-09", "clipped": False}
    assert r["summary"] == {"start_score": 690, "end_score": 650, "net_change": -40,
                            "lowest": {"date": "2026-09-01", "score": 650},
                            "highest": {"date": "2026-08-01", "score": 670}}


def test_t3_single_month():
    r = get_score_history("USR-001", "2026-03")
    assert points(r) == [("2026-03-01", 678, 5, "On-time payments")]


def test_t4_all_months():
    r = get_score_history("USR-012", "all")
    assert len(r["points"]) == 12
    assert r["points"][0] == {"date": "2025-10-01", "score": 746, "change": None, "factor_change": "Baseline"}
    assert r["summary"]["start_score"] == 746 and r["summary"]["end_score"] == 684
    assert r["summary"]["net_change"] == -62


def test_t5_window_longer_than_history_is_clipped():
    r = get_score_history("USR-001", "last_24_months")
    assert r["ok"] and len(r["points"]) == 12
    assert r["period"] == {"requested": "last_24_months", "start": "2025-10", "end": "2026-09", "clipped": True}


def test_t6_no_credit_file_is_not_an_error():
    r = get_score_history("USR-004", "latest")
    assert r["ok"] is True and r["has_credit_file"] is False
    assert r["points"] == [] and r["summary"] is None and r["available"] is None
    assert "no credit file" in r["note"]


def test_t7_period_out_of_range():
    r = get_score_history("USR-001", "2025-01")
    assert r == {"ok": False, "error": {
        "code": "PERIOD_OUT_OF_RANGE",
        "message": "No score history for 2025-01. History on file runs from 2025-10 to 2026-09.",
        "retryable": False,
        "details": {"requested": "2025-01", "available": AVAILABLE}}}


def test_t8_invalid_period():
    r = get_score_history("USR-001", "last quarter")
    assert not r["ok"] and r["error"]["code"] == "INVALID_PERIOD" and r["error"]["retryable"] is False
    assert "points" not in r  # an error never carries partial data


@pytest.mark.parametrize("period", ["latest", "all", "last_3_months"])
def test_t15_only_the_requested_users_rows(period):
    for uid in common.tables()[0].user_id:
        r = get_score_history(uid, period)
        assert r["ok"] and r["user_id"] == uid
        own = common.tables()[2]
        own_dates = set(own[own.user_id == uid].date.str[:10])
        assert {p["date"] for p in r["points"]} <= own_dates


# ---- Period forms and edge cases ----

def test_range_form_and_change_across_window_edge():
    r = get_score_history("USR-001", "2026-07:2026-09")
    assert [p["score"] for p in r["points"]] == [690, 670, 650]
    assert r["points"][0]["change"] == 6  # from June's 684, which is outside the window
    assert r["summary"]["start_score"] == 684 and r["summary"]["net_change"] == -34


def test_range_running_past_as_of_is_clipped():
    r = get_score_history("USR-001", "2026-08:2026-12")
    assert r["period"] == {"requested": "2026-08:2026-12", "start": "2026-08", "end": "2026-09", "clipped": True}


def test_range_entirely_before_history_is_out_of_range():
    r = get_score_history("USR-001", "2024-01:2025-09")
    assert r["error"]["code"] == "PERIOD_OUT_OF_RANGE"
    assert r["error"]["message"].startswith("No score history for 2024-01 to 2025-09.")


@pytest.mark.parametrize("period", [" LATEST ", "Last_3_Months", "last_1_month"])
def test_forms_are_case_and_space_insensitive(period):
    assert get_score_history("USR-001", period)["ok"]


def test_requested_is_echoed_as_given():
    assert get_score_history("USR-001", " LATEST ")["period"]["requested"] == " LATEST "


@pytest.mark.parametrize("period", ["2026-13", "2026-00", "26-03", "last_0_months", "last_25_months",
                                    "last_n_months", "2026-09:2026-01", "", "   ", None, 202603, "this month"])
def test_invalid_periods(period):
    assert get_score_history("USR-001", period)["error"]["code"] == "INVALID_PERIOD"


def test_invalid_period_wins_over_no_credit_file():
    assert get_score_history("USR-007", "last quarter")["error"]["code"] == "INVALID_PERIOD"


def test_no_credit_file_never_out_of_range():
    r = get_score_history("USR-007", "2025-01")
    assert r["ok"] and r["has_credit_file"] is False


@pytest.mark.parametrize("user_id", ["USR-999", "usr-001", "", None, "USR-001 ", "Aravind"])
def test_unknown_user(user_id):
    r = get_score_history(user_id, "latest")
    assert r["error"]["code"] == "UNKNOWN_USER" and r["error"]["details"] == {"user_id": user_id}


def test_new_interview_users_are_served():
    r = get_score_history("USR-015", "all")
    assert r["ok"] and len(r["points"]) == 12 and r["summary"]["start_score"] == 733


def test_every_change_matches_the_data():
    """For every user with history: change = score - previous score, and net_change = sum of changes."""
    for uid in common.tables()[0].user_id:
        r = get_score_history(uid, "all")
        if not r["has_credit_file"]:
            continue
        scores = [p["score"] for p in r["points"]]
        assert [p["change"] for p in r["points"]] == [None] + [b - a for a, b in zip(scores, scores[1:])]
        assert r["summary"]["net_change"] == sum(p["change"] for p in r["points"][1:])


def test_missing_data_file_is_data_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    common.tables.cache_clear()
    try:
        r = get_score_history("USR-001", "latest")
        assert r["error"]["code"] == "DATA_UNAVAILABLE" and r["error"]["retryable"] is True
    finally:
        common.tables.cache_clear()  # later tests read the real files again


def test_data_matches_csv_directly():
    """Cross-check a full history against the CSV read independently of the tool."""
    csv = pd.read_csv(config.DATA_DIR / "score_history.csv")
    mine = csv[csv.user_id == "USR-009"]
    r = get_score_history("USR-009", "all")
    assert [(p["date"], p["score"], p["factor_change"]) for p in r["points"]] == \
        [(d, s, f) for d, s, f in zip(mine.date, mine.score, mine.primary_factor_change)]
