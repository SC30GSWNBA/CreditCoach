"""The My credit tab: charts built from the signed-in user's own score history and accounts.

No API key or browser needed: the chart functions are pure, and the page handlers run with a fake request.

Run:
    uv run pytest tests/test_charts.py -v
"""

from types import SimpleNamespace

import pytest

from creditcoach import config
from creditcoach.app import charts as C
from creditcoach.app import main
from creditcoach.tools.account_summary import get_account_summary
from creditcoach.tools.score_history import get_score_history


@pytest.fixture(autouse=True)
def memory_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEMORY_DIR", tmp_path / "memory")


def history(user_id, months=12):
    return get_score_history(user_id, C.period_arg(months))


def request(n):
    return SimpleNamespace(username=f"creditcoach_user{n}", session_hash=f"test-{n}")


def test_inr_uses_indian_grouping():
    assert [C.inr(n) for n in (999, 1000, 74750, 799750, 5450000)] == \
        ["₹999", "₹1,000", "₹74,750", "₹7,99,750", "₹54,50,000"]


def test_paydown_to_30_matches_the_data():
    assert C.paydown_to_30(59000, 75000) == 36500      # USR-001 ACC-01, 78.7% -> 30%
    assert C.paydown_to_30(378100, 455000) == 241600   # USR-012 ACC-20, 83% -> 30%
    assert C.paydown_to_30(11000, 100000) == 0         # already under 30%
    assert C.paydown_to_30(22501, 75000) == 100        # rounds up to the next ₹100, never down


@pytest.mark.parametrize("user_id", ["USR-001", "USR-003", "USR-009", "USR-011", "USR-012", "USR-005"])
@pytest.mark.parametrize("months", [3, 6, 12])
def test_reasons_add_up_to_the_net_change(user_id, months):
    h = history(user_id, months)
    assert sum(points for _, points, _ in C.reasons(h)) == h["summary"]["net_change"]


def test_reasons_put_the_biggest_loss_first():
    f, points, n = C.reasons(history("USR-009"))[0]
    assert (f, points, n) == ("Late payment (30+ days)", -82, 1)


def test_story_figure_shares_one_month_axis_and_dims_other_reasons():
    fig = C.story_figure(history("USR-001"), highlight="Utilization spike")
    floor, line, bars = fig.data
    assert line.yaxis in (None, "y") and bars.yaxis == "y2" and fig.layout.hoversubplots == "axis"
    assert len(bars.x) == 11                              # the baseline month has no change
    lit = [o for o in bars.marker.opacity if o == 1]
    assert len(lit) == 1                                  # only Aug 2026 is a plain "Utilization spike"
    assert any(s.y0 == C.STRONG_SCORE for s in fig.layout.shapes)


def test_snapshot_shows_the_tools_figures():
    html = C.snapshot_html(history("USR-001"), get_account_summary("USR-001"), "Buying a car")
    for text in ("650", "100 points below 750", "-12", "37.4%", "Above 30%", "₹7,99,750", "3 cards · 2 loans",
                 "Buying a car"):
        assert text in html


def test_no_card_user_gets_no_ratio_not_zero():
    a = get_account_summary("USR-005")
    assert C.cards(a) == [] and C.highest_card(a) is None
    assert "No credit card" in C.cards_html(a) and "cc-track" not in C.cards_html(a)  # no bar drawn
    assert "No credit card" in C.snapshot_html(history("USR-005"), a)


def test_whatif_moves_only_the_picked_card():
    a = get_account_summary("USR-001")
    html = C.cards_html(a, "ACC-01", 36500)
    assert "₹22,500 of ₹75,000" in html and "(now 78.7%)" in html
    assert "₹11,000 of ₹1,00,000" in html                 # ACC-02 untouched
    assert "₹38,250 of ₹2,00,000" in html                 # all cards: 74,750 - 36,500
    assert C.whatif_note(a, "ACC-01", 36500).startswith("Paying ₹36,500 brings ACC-01 to **30%**. This")
    assert "It takes ₹36,500 to reach 30%" in C.whatif_note(a, "ACC-01", 10000)
    assert "doesn't predict a score" in C.whatif_note(a, "ACC-01")


def test_instant_loan_app_is_flagged_high_risk():
    assert "High risk" in C.debt_html(get_account_summary("USR-012"))
    assert "High risk" not in C.debt_html(get_account_summary("USR-001"))


def test_month_question_and_choices():
    choices = C.month_choices(history("USR-011", 3))
    assert choices[0] == ("Sep 2026: 692 (+1)", "2026-09-01")
    assert C.month_question("2026-08-01") == "Why did my score change in Aug 2026?"


def test_page_uses_only_the_signed_in_users_data(monkeypatch):
    seen = []
    real_history, real_accounts = main.get_score_history, main.get_account_summary
    monkeypatch.setattr(main, "get_score_history", lambda u, p: seen.append(u) or real_history(u, p))
    monkeypatch.setattr(main, "get_account_summary", lambda u: seen.append(u) or real_accounts(u))
    out = main.load_credit(12, request(11))
    assert set(seen) == {"USR-011"}
    assert out[0]["visible"] is True and "692" in out[4]


def test_no_credit_file_shows_the_empty_state():
    out = main.load_credit(12, request(4))                # USR-004 Ananya: no cards, no loans
    assert out[0]["visible"] is False and out[1]["visible"] is True
    assert "No credit history yet" in out[2] and "Ananya" in out[2]


def test_signed_out_request_shows_nothing():
    out = main.load_credit(12, SimpleNamespace(username=None, session_hash="x"))
    assert out[0]["visible"] is False and "unavailable" in out[2]


def test_ask_about_month_fills_the_chat_box():
    box, tabs = main.ask_about_month("2026-08-01")
    assert box["value"] == "Why did my score change in Aug 2026?"
    assert tabs.selected == "chat"
