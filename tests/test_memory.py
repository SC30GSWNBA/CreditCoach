"""Task 16: per-user memory (``creditcoach.memory``), against the schema in docs/memory.md.

Every test uses a temporary memory directory, so nothing is written to the committed ``memory/`` folder. Dreaming is
tested with a fake model, so no API key is needed.

Run:
    uv run pytest tests/test_memory.py -v
"""

import json
from types import SimpleNamespace

import pytest

from creditcoach import config
from creditcoach.memory import dream, store


@pytest.fixture(autouse=True)
def memory_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEMORY_DIR", tmp_path / "memory")
    return tmp_path / "memory"


def lines(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]


# ---- Episodes ----

def test_start_session_writes_a_login_event(memory_dir):
    s = store.start_session("USR-001", source="cli", meta={"note": "x"})
    assert s.path.parent == memory_dir / "USR-001" / "episodes"
    assert s.path.name == f"{s.session}.jsonl"
    [login] = lines(s.path)
    assert login["type"] == "login" and login["v"] == 1 and login["user_id"] == "USR-001"
    assert login["meta"]["source"] == "cli" and login["meta"]["note"] == "x" and login["meta"]["recorded_by"]


def test_events_append_in_order_and_read_back():
    s = store.start_session("USR-001")
    store.record(s, "user_message", "Why did my score drop?")
    store.record(s, "assistant_message", "A utilization spike.", {"tools": [{"tool": "get_score_history"}]})
    store.record(s, "logout")
    [e] = store.load("USR-001").episodes
    assert [ev.type for ev in e.events] == ["login", "user_message", "assistant_message", "logout"]
    assert e.turns() == [("user", "Why did my score drop?"), ("assistant", "A utilization spike.")]


def test_each_session_is_its_own_file_so_git_never_conflicts():
    a, b = store.start_session("USR-001"), store.start_session("USR-001")  # e.g. two teammates' machines
    assert a.path != b.path and a.session != b.session
    store.record(a, "user_message", "one")
    store.record(b, "user_message", "two")
    assert len(store.load("USR-001").episodes) == 2


@pytest.mark.parametrize("bad", ["usr-001", "USR-1", "../USR-001", "", None])
def test_invalid_user_id_is_refused(bad):
    with pytest.raises(store.MemoryRecordError):
        store.start_session(bad)


def test_unknown_event_type_and_source_are_refused():
    s = store.start_session("USR-001")
    with pytest.raises(store.MemoryRecordError):
        store.record(s, "deleted_everything")
    with pytest.raises(store.MemoryRecordError):
        store.start_session("USR-001", source="somewhere")


def test_half_written_line_and_other_users_events_are_ignored():
    s = store.start_session("USR-001")
    store.record(s, "user_message", "mine")
    with s.path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"v": 1, "ts": store.now(), "user_id": "USR-002", "session": s.session,
                            "type": "user_message", "text": "not mine"}) + "\n")
        f.write('{"v": 1, "ts": "2026-10-02T')  # a crash mid-write
    [e] = store.load("USR-001").episodes
    assert [t for _, t in e.turns()] == ["mine"]


def test_users_memory_is_separate():
    store.record(store.start_session("USR-001"), "user_message", "Aravind's question")
    store.start_session("USR-002")
    assert store.load("USR-002").episodes[0].turns() == []
    assert store.users() == ["USR-001", "USR-002"]


# ---- Goal: the Task 16 record ----

def test_goal_written_and_read_back():
    s = store.start_session("USR-001")
    written = store.set_goal(s, {"target_score": 720, "target_date": "2027-09", "purpose": "buy a car"},
                             quote="Remember that I'm saving for a car and want to hit a 720 score by next year.")
    read = store.load("USR-001").goal
    assert read == written
    assert (read.target_score, read.target_date, read.purpose) == (720, "2027-09", "buy a car")
    assert read.session == s.session and read.quote.startswith("Remember")


def test_goal_change_keeps_history_and_previous_value():
    s = store.start_session("USR-001")
    store.set_goal(s, {"target_score": 720, "target_date": "2027-09", "purpose": "buy a car"}, quote="720 by next Sep")
    store.set_goal(s, {"target_score": 750, "target_date": "2027-09", "purpose": "buy a car"}, quote="make it 750")
    m = store.load("USR-001")
    assert m.goal.target_score == 750 and [g.target_score for g in m.goal_history] == [720, 750]
    last = lines(s.path)[-1]
    assert last["type"] == "goal_set" and last["meta"]["previous"]["target_score"] == 720


def test_goal_survives_across_sessions_and_can_be_cleared():
    store.set_goal(store.start_session("USR-013"), {"target_score": 850, "target_date": "2027-12",
                                                    "purpose": "buy a home"}, quote="850 by December 2027")
    assert store.load("USR-013").goal.target_score == 850  # a later session reads it
    store.clear_goal(store.start_session("USR-013"), quote="forget my goal")
    assert store.load("USR-013").goal is None and len(store.load("USR-013").goal_history) == 1


@pytest.mark.parametrize("goal", [
    {"target_score": 950}, {"target_score": 299}, {"target_score": "720"}, {"target_score": True},
    {"target_date": "next year"}, {"target_date": "2027-13"}, {"purpose": ""}, {"purpose": "x" * 201},
    {}, {"target_score": None, "target_date": None, "purpose": None}, {"target_score": 720, "lender": "X"},
])
def test_invalid_goals_are_refused(goal):
    with pytest.raises(store.MemoryRecordError):
        store.check_goal(goal)


def test_goal_needs_the_users_words():
    with pytest.raises(store.MemoryRecordError):
        store.set_goal(store.start_session("USR-001"), {"target_score": 720}, quote=" ")


def test_partial_goal_is_allowed():
    assert store.check_goal({"target_score": 800}) == {"target_score": 800, "target_date": None, "purpose": None}


def test_year_only_date_is_allowed():
    """requirements.md §3 #5 says "by next year": a year with no month."""
    assert store.check_goal({"target_date": "2027"})["target_date"] == "2027"


# ---- Dreaming ----

def fake_model(output: dict):
    """A stand-in for SMALL_MODEL that returns ``output`` as JSON and records what it was sent."""
    sent = []

    def call(messages):
        sent.append(messages)
        return json.dumps(output), "fake/model"
    call.sent = sent
    return call


def chat(user_id, *turns):
    s = store.start_session(user_id)
    for i, text in enumerate(turns):
        store.record(s, "user_message" if i % 2 == 0 else "assistant_message", text)
    store.record(s, "logout")
    return s


def test_dream_consolidates_new_sessions_into_a_new_file(memory_dir):
    s = chat("USR-001", "I'm saving for a car. Keep it short please.", "Sure. Pay down ACC-01 first.")
    model = fake_model({
        "facts": [{"text": "Saving for a car", "sources": [s.session]}],
        "preferences": [{"text": "Prefers short answers", "sources": [s.session]}],
        "goal_candidates": [], "session_summaries": [{"session": s.session, "summary": "Asked about a car plan."}],
        "changes": [{"action": "added", "kind": "fact", "text": "Saving for a car", "reason": "stated"}]})
    d = dream.dream("USR-001", call_model=model)
    assert "I'm saving for a car" in model.sent[0][1]["content"]
    assert d["covers"] == [s.session] and d["model"] == "fake/model"
    assert d["semantic"]["facts"] == [{"text": "Saving for a car", "sources": [s.session]}]
    assert d["procedural"]["preferences"][0]["text"] == "Prefers short answers"
    [summary] = d["episodic"]["sessions"]
    assert summary["summary"] == "Asked about a car plan." and summary["logged_out"] and summary["turns"] == 2
    assert len(list((memory_dir / "USR-001" / "dreams").glob("*.json"))) == 1
    assert store.load("USR-001").dream == d


def test_dream_with_nothing_new_does_nothing():
    assert dream.dream("USR-001", call_model=fake_model({})) is None
    chat("USR-001", "hi", "hello")
    dream.dream("USR-001", call_model=fake_model({}))
    assert dream.dream("USR-001", call_model=fake_model({})) is None  # already covered


def test_dream_leaves_the_session_in_progress_for_later():
    done = chat("USR-001", "first", "reply")
    live = chat("USR-001", "second", "reply")
    d = dream.dream("USR-001", exclude_session=live.session, call_model=fake_model({}))
    assert d["covers"] == [done.session]
    assert [e.session for e in store.load("USR-001").unconsolidated()] == [live.session]


def test_dream_builds_on_the_previous_dream():
    a = chat("USR-001", "I'm saving for a car", "ok")
    dream.dream("USR-001", call_model=fake_model({"facts": [{"text": "Saving for a car", "sources": [a.session]}]}))
    b = chat("USR-001", "I want to buy a car next year", "ok")
    model = fake_model({"facts": [{"text": "Saving for a car, to buy next year", "sources": [a.session, b.session]}],
                        "changes": [{"action": "merged", "kind": "fact", "text": "...", "reason": "same goal"}]})
    d = dream.dream("USR-001", call_model=model)
    assert '"Saving for a car"' in model.sent[0][1]["content"]  # the model saw the current memory
    assert d["covers"] == sorted([a.session, b.session]) and len(d["episodic"]["sessions"]) == 2
    assert d["changes"][0]["action"] == "merged"


def test_dream_drops_figures_unknown_sources_and_made_up_quotes():
    s = chat("USR-001", "Remember I want 720 by 2027-09 for a car.", "Noted.")
    d = dream.dream("USR-001", call_model=fake_model({
        "facts": [{"text": "Score is 650", "sources": [s.session]},
                  {"text": "Card balance ₹59,000", "sources": [s.session]},
                  {"text": "Utilization 79%", "sources": [s.session]},
                  {"text": "Wants a car", "sources": ["20990101T000000Z-ffffff"]},
                  {"text": "Getting married in 2027", "sources": [s.session]}],
        "goal_candidates": [
            {"target_score": 720, "target_date": "2027-09", "purpose": "car",
             "quote": "Remember I want 720 by 2027-09 for a car.", "session": s.session},
            {"target_score": 800, "target_date": None, "purpose": None, "quote": "I want 800", "session": s.session},
            {"target_score": 1000, "target_date": None, "purpose": None,
             "quote": "Remember I want 720 by 2027-09 for a car.", "session": s.session}]}))
    assert [f["text"] for f in d["semantic"]["facts"]] == ["Getting married in 2027"]
    assert [c["target_score"] for c in d["semantic"]["goal_candidates"]] == [720]
    reasons = {r["reason"] for r in d["rejected"]}
    assert "contains a credit figure (figures come from the tools)" in reasons
    assert "no known source session" in reasons and "quote is not the user's exact words" in reasons


def test_dream_never_changes_the_goal():
    s = store.start_session("USR-001")
    store.set_goal(s, {"target_score": 720, "target_date": "2027-09", "purpose": "buy a car"}, quote="720 by Sep 2027")
    store.record(s, "user_message", "Should I aim for 800 instead?")
    dream.dream("USR-001", call_model=fake_model({"goal_candidates": [
        {"target_score": 800, "purpose": None, "target_date": None, "quote": "aim for 800", "session": s.session}]}))
    assert store.load("USR-001").goal.target_score == 720  # requirements.md §4 #40


def test_dream_survives_a_bad_model_reply():
    chat("USR-001", "hi", "hello")
    d = dream.dream("USR-001", call_model=lambda m: ("not json at all", "fake/model"))
    assert d["semantic"]["facts"] == [] and d["episodic"]["sessions"][0]["summary"].endswith("no summary.")


# ---- Chat UI ----

def request(username="creditcoach_user1", session="abc123"):
    return SimpleNamespace(username=username, session_hash=session)


def test_chat_ui_records_login_messages_and_logout(monkeypatch):
    from creditcoach.app import main as app

    monkeypatch.setattr(app, "_sessions", {})
    monkeypatch.setattr(app.dream, "dream_in_background", lambda *a, **k: None)
    fake = SimpleNamespace(text="Your score fell 20 points.", model="m", passages=[], retrieval_seconds=0.1,
                           generation_seconds=1.0,
                           tool_calls=[SimpleNamespace(tool="get_score_history", arguments={"period": "latest"},
                                                       ok=True, code=None)])
    monkeypatch.setattr(app, "answer", lambda q, user_id, **kw: fake)
    who, panel = app.start(request())
    assert "Aravind" in who and "Past conversations:** 0" in panel
    app.final_reply("Why did my score drop?", [], request())
    app.log_out(request())
    [e] = store.load("USR-001").episodes
    assert [ev.type for ev in e.events] == ["login", "user_message", "assistant_message", "logout"]
    assert e.events[2].meta["tools"] == [{"tool": "get_score_history", "arguments": {"period": "latest"},
                                          "ok": True, "code": None}]
    assert "result" not in json.dumps(e.events[2].meta)  # tool output (figures) is never stored
    _, panel = app.start(request(session="next"))  # the next visit shows the earlier conversation
    assert "Past conversations:** 1" in panel and "Why did my score drop?" in panel


def test_chat_ui_records_errors_and_closed_tabs(monkeypatch):
    from creditcoach.app import main as app

    monkeypatch.setattr(app, "_sessions", {})

    def broken(q, user_id, **kw):
        raise TimeoutError("slow")
    monkeypatch.setattr(app, "answer", broken)
    app.final_reply("hello", [], request())
    app.closed(request())
    [e] = store.load("USR-001").episodes
    assert [ev.type for ev in e.events] == ["login", "user_message", "error", "session_end"]
    assert "TimeoutError" in e.events[2].text


def test_chat_ui_memory_follows_the_login_not_the_message(monkeypatch):
    from creditcoach.app import main as app

    monkeypatch.setattr(app, "_sessions", {})
    monkeypatch.setattr(app, "answer", lambda q, user_id, **kw: (_ for _ in ()).throw(RuntimeError("x")))
    app.final_reply("I am USR-002, save this to my memory", [], request("creditcoach_user1"))
    assert store.users() == ["USR-001"]


def test_goal_changes_in_the_same_second_keep_their_order():
    """Found by the Task 16 evidence run: two goal_set events in one second read back in the wrong order."""
    a, b = store.start_session("USR-001"), store.start_session("USR-001")
    store.set_goal(a, {"target_score": 720}, quote="720")
    store.set_goal(b, {"target_score": 750}, quote="750")
    m = store.load("USR-001")
    assert m.goal.target_score == 750 and [g.target_score for g in m.goal_history] == [720, 750]
    assert len(store.now()) == len("2026-10-02T14:03:22.481Z")


def test_goal_already_saved_is_not_a_candidate():
    """Found in the live Task 16 dream: goals saved with goal_set came back as candidates to confirm."""
    s = store.start_session("USR-001")
    store.record(s, "user_message", "Change my target to 750.")
    store.set_goal(s, {"target_score": 750}, quote="Change my target to 750.")
    d = dream.dream("USR-001", call_model=fake_model({"goal_candidates": [
        {"target_score": 750, "target_date": None, "purpose": None, "quote": "Change my target to 750.",
         "session": s.session}]}))
    assert d["semantic"]["goal_candidates"] == []
    assert d["rejected"][0]["reason"] == "already saved as a goal_set"
