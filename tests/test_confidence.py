"""The confidence line under each chat answer: the checks, the percentage and where the line goes in the reply.

No API key needed: answers are written by hand around USR-001's real tool results.

Run:
    uv run pytest tests/test_confidence.py -v
"""

import json
from types import SimpleNamespace

from creditcoach.agent import pipeline
from creditcoach.agent.mcp_host import ToolCall
from creditcoach.app import confidence
from creditcoach.evals import golden
from creditcoach.memory import recall
from creditcoach.tools.account_summary import get_account_summary
from creditcoach.tools.common import error
from creditcoach.tools.score_history import get_score_history

PASSAGE = SimpleNamespace(id="credit-utilization#01", title="Credit utilization",
                          text="Utilization above roughly 30% is associated with score drops.")
GROUNDED = ("Your score is 650. Card ACC-01 is at 78.7% (₹59,000 ÷ ₹75,000). 30% of ₹75,000 is ₹22,500, so paying "
            "₹36,500 would bring it there [1].")


def call(tool, result):
    return ToolCall(tool=tool, arguments={}, user_id="USR-001", result=result, seconds=0.01, attempts=1)


def answer(text, calls=None, passages=(PASSAGE,)):
    """A pipeline answer for USR-001 with both tools read, unless ``calls`` says otherwise."""
    if calls is None:
        calls = [call("get_score_history", get_score_history("USR-001", "last_12_months")),
                 call("get_account_summary", get_account_summary("USR-001"))]
    sources = "\n".join(["How do I fix my card?", *(p.text for p in passages),
                         *(json.dumps(c.result, ensure_ascii=False) for c in calls)])
    return pipeline.Answer(question="How do I fix my card?", user_id="USR-001", text=text, model="m",
                           passages=list(passages), tool_calls=calls, sources=sources)


def test_grounded_answer_is_high():
    c = confidence.assess(answer(GROUNDED))
    assert (c.percent, c.untraced) == (90, [])
    assert confidence.line(c) == "**Confidence: 90%** · every figure traces to your live data or the library"


def test_answer_without_figures_is_high():
    c = confidence.assess(answer("Paying on time matters most [1]."))
    assert c.percent == 90 and "no figures" in c.reasons[0]


def test_an_invented_figure_is_named_as_the_answer_writes_it():
    c = confidence.assess(answer(GROUNDED + " Your total limit is ₹4,13,000."))
    assert (c.percent, c.untraced) == (80, ["₹4,13,000"])  # 1 of 8 figures: the least a miss costs
    assert "couldn't trace ₹4,13,000" in confidence.line(c) and "double-check it" in confidence.line(c)


def test_data_that_could_not_be_read_is_low():
    failed = call("get_account_summary", error("DATA_UNAVAILABLE", "timed out", retryable=True))
    c = confidence.assess(answer("I can't pull your accounts right now. Please try again shortly.",
                                 calls=[call("get_score_history", get_score_history("USR-001", "latest")), failed]))
    assert c.percent == 50 and "couldn't read your accounts" in c.reasons[0]


def test_a_failed_call_that_later_succeeded_is_not_a_problem():
    calls = [call("get_score_history", error("INVALID_PERIOD", "bad period")),
             call("get_score_history", get_score_history("USR-001", "latest"))]
    assert confidence.assess(answer("Your score is 650.", calls=calls)).percent == 90


def test_the_more_of_an_answers_figures_are_untraced_the_lower_it_scores():
    some = confidence.assess(answer(GROUNDED + " Your total limit is ₹4,13,000."))
    all_ = confidence.assess(answer("Your limit is ₹4,13,000 and you owe ₹91,300."))
    assert all_.percent == 50 < some.percent


def test_library_gap_bad_citation_and_promise_each_take_points_off():
    gap = confidence.assess(answer("I don’t have specific information on that in CreditCoach's library."))
    cite = confidence.assess(answer("Paying on time matters most [4]."))
    promise = confidence.assess(answer("Do this and your score will reach 650."))
    assert [gap.percent, cite.percent, promise.percent] == [70, 80, 75]
    assert "library doesn't cover" in gap.reasons[0] and "cites a source" in cite.reasons[0]
    assert "promise" in promise.reasons[0]


def test_problems_add_up_but_never_below_the_floor():
    c = confidence.assess(answer("I don't have specific information on that. Your limit is ₹4,13,000."))
    assert c.percent == 30 and len(c.reasons) == 2
    failed = [call(t, error("DATA_UNAVAILABLE", "timed out", retryable=True)) for t in confidence.DATA_TOOLS]
    assert confidence.assess(answer("I don't have specific information on that.", calls=failed)).percent == 10


def test_untraced_numbers_follow_the_answers_own_working():
    sources = '{"balance_inr": 59000, "credit_limit_inr": 75000, "total_balance_inr": 74750, "as_of": "2026-09-01"}'
    worked = "30% of ₹75,000 is ₹22,500, so pay ₹36,500, leaving ₹38,250 overall by 2027."
    assert golden.untraced_numbers(worked, sources, known=frozenset({"30"})) == []
    assert golden.untraced_numbers("You'll owe ₹41,300 by 2040.", sources) == ["2040", "41300"]


def test_reply_shows_the_line_above_the_sources_and_history_drops_it():
    from creditcoach.app import main as app

    reply = app.format_reply(answer(GROUNDED))
    assert reply.index("**Confidence: 90%**") < reply.index("**Sources from the CreditCoach library**")
    assert recall.history_messages([{"role": "assistant", "content": reply}]) == [
        {"role": "assistant", "content": GROUNDED}]


def test_reply_survives_a_failing_confidence_check(monkeypatch):
    from creditcoach.app import main as app

    monkeypatch.setattr(confidence, "assess", lambda a: 1 / 0)
    reply = app.format_reply(answer(GROUNDED))
    assert reply.startswith(GROUNDED) and "Confidence" not in reply and "**Sources" in reply


def test_answer_keeps_what_the_model_was_given_as_sources(monkeypatch):
    monkeypatch.setattr(pipeline, "retrieve", lambda q, k=3: [])
    monkeypatch.setattr(pipeline, "load_system_prompt", lambda: "SYSTEM PROMPT 123456")
    monkeypatch.setattr(pipeline, "chat_with_tools", lambda messages, tools: (
        SimpleNamespace(content="Your score is 650.", tool_calls=None), "m"))
    a = pipeline.answer("What's my score?", user_id="USR-001")
    assert "What's my score?" in a.sources and '"score": 650' in a.sources and "123456" not in a.sources
    assert confidence.assess(a).percent == 90
