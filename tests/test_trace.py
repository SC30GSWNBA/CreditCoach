"""Task 18: the agent trace in the chat: live progress while waiting, then an expandable record of the answer.

No API key needed: progress events are scripted, and the streaming chat handler runs with a fake ``answer``.

Run:
    uv run pytest tests/test_trace.py -v
"""

from types import SimpleNamespace

import pytest

from creditcoach import config
from creditcoach.agent.mcp_host import ToolCall
from creditcoach.app import trace as T
from creditcoach.memory import store
from creditcoach.tools.account_summary import get_account_summary
from creditcoach.tools.score_history import get_score_history


@pytest.fixture(autouse=True)
def memory_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEMORY_DIR", tmp_path / "memory")


def call(tool, result, attempts=1):
    return ToolCall(tool=tool, arguments={}, user_id="USR-001", result=result, seconds=0.01, attempts=attempts)


def meta(messages):
    return [(m.metadata.get("title", ""), m.metadata.get("status"), m.metadata.get("parent_id")) for m in messages]


GOAL = store.Goal(target_score=720, target_date="2027", purpose="buy a car", set_at="2026-10-02T10:00:00.000Z",
                  session="s", quote="q")
PASSAGES = [SimpleNamespace(title="Why did my credit score drop?"), SimpleNamespace(title="Credit utilization")]


def full_run(t):
    t.update("retrieval", {"status": "start"})
    t.update("retrieval", {"status": "done", "passages": PASSAGES, "seconds": 0.4})
    t.update("memory", {"goal": GOAL, "sessions": 2})
    t.update("model", {"round": 1})
    t.update("tool", {"status": "start", "name": "get_score_history", "arguments": {"period": "latest"}})
    t.update("tool", {"status": "done", "call": call("get_score_history", get_score_history("USR-001", "latest"))})
    t.update("model", {"round": 2})
    t.update("answer", {"status": "done", "model": "m"})


def test_live_steps_while_waiting():
    t = T.Trace(question="Why did my score drop?")
    t.update("retrieval", {"status": "start"})
    [parent, step] = t.messages()
    assert parent.metadata["status"] == "pending" and parent.metadata["title"].startswith("🧭 Working on your answer")
    assert step.metadata["parent_id"] == T.TRACE_ID and step.metadata["status"] == "pending"
    assert step.metadata["title"].startswith("📚 Searching the CreditCoach library…")


def test_finished_trace_lists_tools_goal_and_passages():
    t = T.Trace(question="Why did my score drop?")
    full_run(t)
    msgs = t.messages()
    titles = [m.metadata["title"] for m in msgs]
    assert titles[0].startswith("🧭 Agent trace · 5 steps, 1 tool call")
    assert all(m.metadata["status"] == "done" for m in msgs) and all("duration" in m.metadata for m in msgs)
    assert titles[1:] == ["📚 Searched the CreditCoach library", "🧠 Recalled your memory",
                          "🤔 Read your question and decided what to check",
                          "📈 Checking your score history (period=latest)", "✍️ Wrote your answer"]
    by_title = {m.metadata["title"]: m.content for m in msgs}
    assert "• Why did my credit score drop?" in by_title["📚 Searched the CreditCoach library"]
    assert "Goal: target 720, by 2027, buy a car" in by_title["🧠 Recalled your memory"]
    assert "2 earlier conversations" in by_title["🧠 Recalled your memory"]
    assert "Latest: 650 (2026-09, -20 that month, Hard inquiry + utilization spike)" in \
        by_title["📈 Checking your score history (period=latest)"]


def test_failed_tool_is_marked_and_explained():
    t = T.Trace()
    t.update("tool", {"status": "start", "name": "get_account_summary", "arguments": {}})
    t.update("tool", {"status": "done", "call": call("get_account_summary", {"ok": False, "error": {
        "code": "DATA_UNAVAILABLE", "message": "get_account_summary took longer than 5 seconds."}}, attempts=2)})
    step = t.messages()[1]
    assert step.metadata["title"] == "⚠️ Reading your accounts and card limits"
    assert step.content.startswith("Couldn't complete after a retry: DATA_UNAVAILABLE")


def test_waiting_tip_appears_only_after_a_pause(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(T.time, "monotonic", lambda: clock[0])
    t = T.Trace(question="q")
    t.update("model", {"round": 1})
    assert t.messages()[1].content == ""
    clock[0] += T.TIP_AFTER + 0.5
    first = t.messages()[1].content
    assert first.startswith("💡 While you wait: ") and first.split(": ", 1)[1] in T.TIPS
    clock[0] += T.TIP_EVERY
    assert t.messages()[1].content != first  # the tip rotates
    assert t.messages()[1].metadata["title"].endswith(f"… {T.TIP_AFTER + 0.5 + T.TIP_EVERY:.0f}s")


def test_tips_are_labelled_typical_where_they_give_ranges():
    for tip in T.TIPS:
        if any(ch.isdigit() for ch in tip) and " to " in tip:
            assert "typically" in tip


@pytest.mark.parametrize("tool,result,expected", [
    ("get_account_summary", get_account_summary("USR-001"), "3 card(s), 2 loan(s). Overall card utilization 37.4%."),
    ("get_account_summary", get_account_summary("USR-012"), "1 high-risk product flagged"),
    ("get_account_summary", get_account_summary("USR-005"), "No credit card, so no utilization."),
    ("get_account_summary", get_account_summary("USR-007"), "No accounts on file yet."),
    ("get_score_history", get_score_history("USR-004", "latest"), "No credit history on file yet."),
    ("get_score_history", get_score_history("USR-001", "2025-01"), "Couldn't complete: PERIOD_OUT_OF_RANGE"),
    ("save_goal", {"ok": True, "goal": {"target_score": 750, "target_date": "2027", "purpose": "buy a car"},
                   "previous": {"target_score": 720, "target_date": "2027", "purpose": "buy a car"}},
     "Saved: 750, 2027, buy a car. Was: 720, 2027, buy a car."),
    ("clear_goal", {"ok": True, "cleared": True}, "Goal cleared."),
])
def test_summaries(tool, result, expected):
    assert expected in T.summarise(call(tool, result))


def test_quote_is_not_shown_in_the_save_goal_step():
    t = T.Trace()
    t.update("tool", {"status": "start", "name": "save_goal", "arguments": {"target_score": 720, "quote": "long words"}})
    assert t.messages()[1].metadata["title"] == "🎯 Saving your goal (target_score=720)…" + " 0s"


# ---- The streaming chat handler ----

def fake_answer(fail=False):
    def answer(question, user_id=None, session=None, history=None, progress=None):
        progress("retrieval", {"status": "start"})
        progress("retrieval", {"status": "done", "passages": PASSAGES, "seconds": 0.1})
        progress("model", {"round": 1})
        if fail:
            raise TimeoutError("slow")
        progress("answer", {"status": "done", "model": "m"})
        return SimpleNamespace(text="Your score fell 20 points.", model="m", passages=PASSAGES[:0],
                               tool_calls=[], retrieval_seconds=0.1, generation_seconds=0.2)
    return answer


def test_respond_streams_the_trace_then_the_answer(monkeypatch):
    from creditcoach.app import main as app

    monkeypatch.setattr(app, "_sessions", {})
    monkeypatch.setattr(app, "answer", fake_answer())
    req = SimpleNamespace(username="creditcoach_user1", session_hash="h1")
    frames = list(app.respond("Why did my score drop?", [], req))
    assert len(frames) >= 3  # first frame shows immediately, then one per event
    assert frames[0][0].metadata["status"] == "pending"
    last = frames[-1]
    assert last[0].metadata["title"].startswith("🧭 Agent trace") and last[0].metadata["status"] == "done"
    assert last[-1].content.startswith("Your score fell 20 points.") and not last[-1].metadata
    events = [e.type for e in store.load("USR-001").episodes[0].events]
    assert events == ["login", "user_message", "assistant_message"]


def test_respond_shows_an_apology_and_records_the_error(monkeypatch):
    from creditcoach.app import main as app

    monkeypatch.setattr(app, "_sessions", {})
    monkeypatch.setattr(app, "answer", fake_answer(fail=True))
    req = SimpleNamespace(username="creditcoach_user1", session_hash="h2")
    last = list(app.respond("hello", [], req))[-1]
    assert last[0].metadata["title"].startswith("🧭 Agent trace · stopped")
    assert last[-1].content == app.APOLOGY
    assert "TimeoutError" in store.load("USR-001").episodes[0].events[-1].text


def test_respond_without_a_question_or_login_needs_no_trace(monkeypatch):
    from creditcoach.app import main as app

    assert list(app.respond("  ", [], SimpleNamespace(username="creditcoach_user1", session_hash="h3"))) == [
        "Please type a question about your credit."]
    assert list(app.respond("hi", [], SimpleNamespace(username=None))) == ["Please sign in again to continue."]


def test_prefetched_data_comes_before_the_first_model_turn():
    """The pipeline fetches both tools before the model's first turn (2026-10-02), so that turn writes the answer."""
    t = T.Trace()
    t.update("tool", {"status": "start", "name": "get_score_history", "arguments": {"period": "last_12_months"}})
    t.update("tool", {"status": "done", "call": call("get_score_history", get_score_history("USR-001", "last_12_months"))})
    t.update("model", {"round": 1})
    assert t.messages()[-1].metadata["title"].startswith("✍️ Writing your answer")
    t.update("tool", {"status": "start", "name": "get_score_history", "arguments": {"period": "all"}})
    assert t.messages()[-2].metadata["title"] == "🤔 Decided to check more of your data"
