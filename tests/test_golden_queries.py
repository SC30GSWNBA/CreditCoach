"""The 50 golden queries (requirements.md §3 and §4) stay in sync with requirements.md, data/ and the tools.

requirements.md §4 says "If the dataset is regenerated, re-check the figures in this table." These tests do that
check on every pull request: every figure an expected answer relies on is read from the live tools and compared
with ``creditcoach/evals/golden_queries.json``, and the figures requirements.md derives from them (paydown amounts,
total debt, gaps to a target) are recomputed.

Run:
    uv run pytest tests/test_golden_queries.py -v
"""

import re

import pytest

from creditcoach.evals import golden
from creditcoach.tools.account_summary import get_account_summary
from creditcoach.tools.common import tables
from creditcoach.tools.score_history import get_score_history

QUERIES = golden.load()
FACTS = [(q.id, f) for q in QUERIES for f in q.facts]


# ---- The set matches requirements.md ----

def test_all_50_queries_in_order():
    assert [q.id for q in QUERIES] == list(range(1, 51))
    assert [q.section for q in QUERIES[:6]] == ["3"] * 6
    assert {q.section for q in QUERIES[6:]} == {"4.1", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7"}


def test_each_query_text_is_in_requirements():
    text = golden.REQUIREMENTS.read_text(encoding="utf-8")
    for q in QUERIES:
        assert f'"{q.query}"' in text, q.id
        assert q.expected and q.expected in text, q.id


def test_users_exist_and_match_requirements():
    users = set(tables()[0].user_id)
    for q in QUERIES:
        assert q.user_id in users, q.id
        assert q.user.startswith(q.user_id), q.id


def test_annotations_are_well_formed():
    for q in QUERIES:
        for group in q.tools:
            assert group and set(group) <= set(golden.TOOL_NAMES.values()), q.id
        for groups in (q.figures, q.behavior):
            assert all(group and all(isinstance(a, str) and a for a in group) for group in groups), q.id
        for pattern in q.forbidden:
            re.compile(pattern)
        assert q.figures or q.behavior or q.forbidden or q.needs, f"query {q.id} has nothing to check"


def test_figure_checks_need_a_tool_call():
    """A query whose answer must state the user's figures must also require the tool those figures come from."""
    for q in QUERIES:
        if q.figures and q.id != 46:
            assert q.tools, q.id


# ---- Every expected figure matches the tools ----

@pytest.mark.parametrize("qid,fact", FACTS, ids=[f"q{qid}-{f.user_id}-{f.tool}-{f.period or ''}-{f.path}" for qid, f in FACTS])
def test_fact_matches_tool(qid, fact):
    holds, actual = golden.check_fact(fact)
    assert holds, f"query {qid}: {fact.path} is {actual!r}, expected {fact.equals if fact.has_equals else 'not ' + repr(fact.excludes)}"


def test_derived_figures_in_requirements():
    """Figures requirements.md calculates from tool output (§4 #12, #16, #17, #25, #36, #42)."""
    a1 = get_account_summary("USR-001")
    totals, acc01 = a1["totals"], golden.resolve(a1, "accounts.ACC-01")
    assert totals["revolving_balance_inr"] - 0.30 * totals["revolving_limit_inr"] == 14750  # #16 overall paydown
    assert acc01["balance_inr"] - 0.30 * acc01["credit_limit_inr"] == 36500  # #16 ACC-01 paydown
    assert 0.30 * acc01["credit_limit_inr"] == 22500
    assert totals["total_balance_inr"] == 74750 + 420000 + 305000 == 799750  # #17
    assert 720 - get_score_history("USR-001", "latest")["points"][0]["score"] == 70  # #25 gap
    assert 850 - get_score_history("USR-013", "latest")["points"][0]["score"] == 9  # #36
    assert 811 - get_score_history("USR-009", "latest")["points"][0]["score"] == 51  # #42
    h12 = get_score_history("USR-012", "latest")
    assert h12["summary"]["start_score"] == 703 and h12["points"][0]["score"] == 684  # #12 latest drop 703 -> 684


def test_users_without_a_query_are_known():
    """data/README.md notes that USR-014 and USR-015 have no §4 query yet. Fail if that changes unnoticed."""
    used = {q.user_id for q in QUERIES} | {f.user_id for q in QUERIES for f in q.facts}
    assert set(tables()[0].user_id) - used == {"USR-014", "USR-015"}


# ---- The answer checks ----

def test_normalize_matches_indian_and_plain_amounts():
    for text in ("₹14,750", "Rs. 14750", "INR 14,750", "14750"):
        assert "14750" in golden.normalize(text)
    assert "-20" in golden.normalize("−20 points")
    assert "can't" in golden.normalize("can’t")


def test_check_answer_passes_a_good_answer():
    q = golden.by_id()[15]
    calls = [type("Call", (), {"tool": "get_account_summary", "ok": True})()]
    text = ("ACC-01 is at 78.7% (₹59,000 ÷ ₹75,000), ACC-02 at 11%, ACC-05 at 19%, and overall 37.4%. "
            "Loans have no limit, so utilization leaves them out.")
    check = golden.check_answer(q, text, calls)
    assert check.ok, check.problems()


def test_check_answer_flags_missing_figure_tool_and_guarantee():
    q = golden.by_id()[15]
    check = golden.check_answer(q, "Your utilization is fine. You will reach 750 next year.", tool_calls=[])
    assert check.missing_tools == [["get_account_summary"]]
    assert ["37.4%"] in check.missing_figures
    assert check.guarantees and not check.ok


def test_check_answer_without_data_skips_figures():
    q = golden.by_id()[2]
    check = golden.check_answer(q, "I can't see your accounts yet. Utilization is balance divided by limit.",
                                with_data=False)
    assert check.ok, check.problems()


def test_forbidden_patterns():
    assert golden.check_answer(golden.by_id()[19], "Your utilization is 0% on cards.").forbidden_hits
    assert not golden.check_answer(golden.by_id()[19], "You have no credit card, so there's no ratio.").forbidden_hits
    assert golden.check_answer(golden.by_id()[49], "Vikram's score is 761.").forbidden_hits


def test_hedged_guarantee_is_allowed():
    assert golden.unhedged_guarantees("I can't guarantee you'll reach 720.") == []
    assert golden.unhedged_guarantees("You will reach 720 by March.")
    # Found in the 2026-10-02 rerun (#41): GPT-5 writes curly apostrophes, and any n't contraction negates.
    assert golden.unhedged_guarantees("Scores aren’t guaranteed.") == []
    assert golden.unhedged_guarantees("I can’t promise a number, and gains wasn't certain.") == []


def test_unsourced_numbers_allow_one_step_calculations():
    sources = ('{"balance_inr": 74750, "credit_limit_inr": 200000, "utilization_ratio": 0.374} '
               "Utilization above roughly 30% is associated with score drops.")  # tool result + passage
    answer = "You're at 37.4%. 30% of ₹2,00,000 is ₹60,000, so pay more than ₹14,750."
    assert golden.unsourced_numbers(answer, sources) == []
    assert golden.unsourced_numbers("You'll gain 45 points.", sources) == ["45"]


def test_normalize_handles_model_typography():
    """Found in the first live run: GPT-5 writes non-breaking hyphens (U+2011) and "11.0%"."""
    assert "high-risk" in golden.normalize("Instant loan apps are high‑risk.")
    assert "11%" in golden.normalize("₹11,000 ÷ ₹1,00,000 = 11.0%")
    assert "2-10" in golden.normalize("about 2–10 points")


def test_warning_about_guarantees_is_not_a_guarantee():
    assert golden.unhedged_guarantees("Guaranteed points and upfront fees are classic red flags of a scam.") == []
    assert golden.unhedged_guarantees("Anyone who promises to remove true negatives is making a false promise.") == []


def test_expected_tool_error_counts_as_a_call():
    q = golden.by_id()[46]
    call = type("Call", (), {"tool": "get_score_history", "ok": False, "code": "PERIOD_OUT_OF_RANGE"})()
    check = golden.check_answer(q, "I don't have January 2025. Your history runs from October 2025.", [call])
    assert check.ok, check.problems()


def test_quoted_guarantee_is_a_mention():
    assert golden.unhedged_guarantees('Try safer options before instant loan apps or "guaranteed" credit repair.') == []


def test_words_ending_in_nt_are_not_negations():
    assert golden.unhedged_guarantees("You will hit 720 if you want it.")
    assert golden.unhedged_guarantees("Every point counts, so you'll reach 720 by March.")


def test_worked_examples_use_no_real_users_figures():
    """#45 (2026-10-02): the prompt's and corpus's worked example used Aravind's real ₹74,750 ÷ ₹2,00,000, so
    when the account tool failed the model stated his utilization as an "example". Examples must match no user."""
    from creditcoach import config
    from creditcoach.prompts import load_system_prompt

    figures = set()
    for user in {q.user_id for q in golden.load() if q.user_id}:
        r = get_account_summary(user)
        if r.get("ok", True) and "totals" in r:
            t = r["totals"]
            figures |= {t.get("revolving_balance_inr"), t.get("revolving_limit_inr"), t.get("total_balance_inr")}
            figures |= {a.get("balance_inr") for a in r.get("accounts", [])}
    figures -= {None, 0}
    texts = [load_system_prompt(), *(p.read_text(encoding="utf-8") for p in (config.ROOT / "corpus").glob("*.md"))]
    for text in texts:
        for example in re.findall(r"₹[\d,]+ ÷ ₹[\d,]+", text):
            amounts = {int(a.replace(",", "")) for a in re.findall(r"₹([\d,]+)", example)}
            assert not amounts & figures, f"{example} uses a real user's figure"
