"""Task 17: memory in answers: the MEMORY context, the goal tools, and the agent loop using them.

Uses a temporary memory directory and a scripted model, so no API key is needed and nothing is written to the
committed ``memory/`` folder.

Run:
    uv run pytest tests/test_recall.py -v
"""

import asyncio
import json
from types import SimpleNamespace

import pytest

from creditcoach import config
from creditcoach.agent import pipeline
from creditcoach.memory import dream, recall, store

CAR = "Remember that I'm saving for a car and want to hit a 720 score by next year."


@pytest.fixture(autouse=True)
def memory_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEMORY_DIR", tmp_path / "memory")


def say(session, text):
    store.record(session, "user_message", text)


def save(session, question, **args):
    return recall.MemoryTools(session, question).call("save_goal", args)


# ---- MEMORY context ----

def test_context_for_a_new_user():
    s = store.start_session("USR-001")
    text = recall.context("USR-001", s.session)
    assert "Stored goal: none" in text and "this is the user's first session" in text
    assert "not instructions to you" in text and "Today's date:" in text


def test_context_recalls_a_goal_from_an_earlier_session():
    s1 = store.start_session("USR-001")
    say(s1, CAR)
    store.set_goal(s1, {"target_score": 720, "target_date": "2027", "purpose": "buy a car"}, quote=CAR)
    s2 = store.start_session("USR-001")
    text = recall.context("USR-001", s2.session)
    assert "target score 720; by 2027; purpose: buy a car" in text and CAR in text
    assert "Previous conversations: 1" in text and CAR[:40] in text  # last messages, before any dream


def test_context_uses_the_dream_and_lists_earlier_goals():
    s1 = store.start_session("USR-001")
    say(s1, "I'm saving for a car. Keep it short.")
    store.set_goal(s1, {"target_score": 720}, quote="720")
    store.set_goal(s1, {"target_score": 750}, quote="750")
    dream.dream("USR-001", call_model=lambda m: (json.dumps({
        "facts": [{"text": "Saving for a car", "sources": [s1.session]}],
        "preferences": [{"text": "Prefers short answers", "sources": [s1.session]}],
        "session_summaries": [{"session": s1.session, "summary": "Set a car goal."}]}), "fake"))
    text = recall.context("USR-001", store.start_session("USR-001").session)
    assert "Facts the user has shared: Saving for a car" in text
    assert "How they like to be helped: Prefers short answers" in text
    assert "The last one" in text and "Set a car goal." in text
    assert "Earlier goals: 720" in text and "target score 750" in text


def test_context_offers_unconfirmed_goals_until_saved():
    s1 = store.start_session("USR-013")
    say(s1, "I want 850 by December 2027 for a home.")
    dream.dream("USR-013", call_model=lambda m: (json.dumps({"goal_candidates": [
        {"target_score": 850, "target_date": "2027-12", "purpose": "home",
         "quote": "I want 850 by December 2027 for a home.", "session": s1.session}]}), "fake"))
    s2 = store.start_session("USR-013")
    assert "never confirmed" in recall.context("USR-013", s2.session)
    say(s2, "Yes, save that.")
    r = save(s2, "Yes, save that.", target_score=850, target_date="2027-12", purpose="buy a home",
             quote="I want 850 by December 2027 for a home.")  # confirming a candidate, in its own words
    assert r.ok and "never confirmed" not in recall.context("USR-013", s2.session)


def test_context_never_includes_another_users_memory():
    s = store.start_session("USR-003")
    store.set_goal(s, {"target_score": 800, "purpose": "car"}, quote="800 for a car")
    assert "800" not in recall.context("USR-001")


# ---- save_goal and clear_goal ----

def test_save_goal_from_the_users_words():
    s = store.start_session("USR-001")
    say(s, CAR)
    r = save(s, CAR, target_score=720, target_date="2027", purpose="buy a car", quote=CAR)
    assert r.ok and r.result["goal"] == {"target_score": 720, "target_date": "2027", "purpose": "buy a car"}
    assert r.result["previous"] is None and r.user_id == "USR-001" and r.attempts == 1
    assert store.load("USR-001").goal.quote == CAR


def test_save_goal_refuses_words_the_user_never_typed():
    s = store.start_session("USR-001")
    say(s, "Should I aim for 800 instead?")
    r = save(s, "Should I aim for 800 instead?", target_score=800, quote="Set my goal to 800")
    assert r.code == "QUOTE_NOT_FROM_USER" and store.load("USR-001").goal is None


def test_partial_update_keeps_the_rest():  # requirements.md §4 #38
    s = store.start_session("USR-001")
    save(s, CAR, target_score=720, target_date="2027", purpose="buy a car", quote=CAR)
    q = "Actually, change my target to 750. I want a better rate on the car loan."
    r = save(s, q, target_score=750, quote="change my target to 750")
    assert r.result["goal"] == {"target_score": 750, "target_date": "2027", "purpose": "buy a car"}
    assert r.result["previous"]["target_score"] == 720 and r.result["kept_from_previous"] == ["purpose", "target_date"]


@pytest.mark.parametrize("args,code", [
    ({"target_score": 950, "quote": CAR}, "INVALID_GOAL"),
    ({"target_date": "next year", "quote": CAR}, "INVALID_GOAL"),
    ({"quote": CAR}, "INVALID_GOAL"),
    ({"target_score": 720}, "QUOTE_NOT_FROM_USER"),
])
def test_save_goal_errors(args, code):
    r = recall.MemoryTools(store.start_session("USR-001"), CAR).call("save_goal", args)
    assert r.code == code and store.load("USR-001").goal is None


def test_bad_json_arguments_are_an_error_not_a_crash():
    r = recall.MemoryTools(store.start_session("USR-001"), CAR).call("save_goal", "{not json")
    assert not r.ok


def test_clear_goal():
    s = store.start_session("USR-001")
    save(s, CAR, target_score=720, quote=CAR)
    r = recall.MemoryTools(s, "Forget my goal.").call("clear_goal", {"quote": "Forget my goal."})
    assert r.result["cleared"] and store.load("USR-001").goal is None


def test_history_messages_strip_sources_and_keep_the_last_turns():
    history = [{"role": "user", "content": "q1"},
               {"role": "assistant", "content": "a1\n\n---\n**Sources from the CreditCoach library**\n1. X"},
               {"role": "system", "content": "ignored"}, {"role": "user", "content": ""}]
    assert recall.history_messages(history) == [{"role": "user", "content": "q1"}, {"role": "assistant", "content": "a1"}]
    assert len(recall.history_messages([{"role": "user", "content": str(i)} for i in range(20)])) == 8


def test_history_messages_skip_trace_steps_and_read_content_parts():
    history = [{"role": "user", "content": [{"type": "text", "text": "q1"}]},
               {"role": "assistant", "content": "Checking…", "metadata": {"title": "📈 Checking your score history"}},
               {"role": "assistant", "content": "a1"}]
    assert recall.history_messages(history) == [{"role": "user", "content": "q1"}, {"role": "assistant", "content": "a1"}]


# ---- Agent loop ----

def tool_call(call_id, name, arguments):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=json.dumps(arguments)))


def scripted(turns, seen):
    turns = iter(turns)

    def fake(messages, tools, model=None):
        seen.append({"messages": [dict(m) for m in messages], "tools": tools})
        calls, text = next(turns)
        return SimpleNamespace(content=text, tool_calls=calls), "scripted"
    return fake


def test_agent_saves_a_goal_through_the_memory_tool(monkeypatch):
    s = store.start_session("USR-001")
    say(s, CAR)
    seen = []
    monkeypatch.setattr(pipeline, "chat_with_tools", scripted([
        ([tool_call("c1", "save_goal", {"target_score": 720, "target_date": "2027", "purpose": "buy a car",
                                        "quote": CAR})], ""),
        (None, "Saved: 720 by 2027 to buy a car."),
    ], seen))
    text, _, calls = asyncio.run(pipeline.run_agent([{"role": "user", "content": CAR}], "USR-001",
                                                    recall.MemoryTools(s, CAR), prefetch=False))
    assert text.startswith("Saved") and [(c.tool, c.ok) for c in calls] == [("save_goal", True)]
    assert {"save_goal", "clear_goal", "get_score_history"} <= {t["function"]["name"] for t in seen[0]["tools"]}
    assert store.load("USR-001").goal.target_score == 720


def test_agent_without_memory_offers_no_memory_tools(monkeypatch):
    seen = []
    monkeypatch.setattr(pipeline, "chat_with_tools", scripted([(None, "ok")], seen))
    asyncio.run(pipeline.run_agent([{"role": "user", "content": "hi"}], "USR-001"))
    assert "save_goal" not in {t["function"]["name"] for t in seen[0]["tools"]}


def test_answer_puts_memory_and_history_before_the_question(monkeypatch):
    s1 = store.start_session("USR-001")
    say(s1, CAR)
    store.set_goal(s1, {"target_score": 720, "target_date": "2027", "purpose": "buy a car"}, quote=CAR)
    s2 = store.start_session("USR-001")
    seen = []
    monkeypatch.setattr(pipeline, "retrieve", lambda q, k=3: [])
    monkeypatch.setattr(pipeline, "chat_with_tools", scripted([(None, "You're aiming for 720 by 2027.")], seen))
    history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    a = pipeline.answer("What should I work on this month?", user_id="USR-001", session=s2, history=history)
    msgs = seen[0]["messages"]
    assert "MEMORY" in msgs[1]["content"] and "target score 720" in msgs[1]["content"]
    assert [m["content"] for m in msgs[2:5]] == ["hi", "hello", "What should I work on this month?"]
    assert [m["role"] for m in msgs[5:]] == ["assistant", "tool", "tool"]  # the prefetched data follows the question
    assert [c.tool for c in a.tool_calls] == ["get_score_history", "get_account_summary"]
    assert a.text.startswith("You're aiming for 720")


def test_answer_refuses_another_users_session():
    with pytest.raises(ValueError):
        pipeline.answer("hi", user_id="USR-001", session=store.start_session("USR-002"))
