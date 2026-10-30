"""The dashboard (Task 31): tool-call failure rate, guardrail triggers and goal-recall accuracy from traces.

No API key or network needed: traces are built here in the local file's shape and in Langfuse's, and Langfuse is
replaced by a stand-in.

Run:
    uv run pytest tests/test_dashboard.py -v
"""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from creditcoach import config
from creditcoach.app import dashboard as D
from creditcoach.app import main

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
GOAL = {"target_score": 720, "target_date": "2027", "purpose": "saving for a car", "session": "S1",
        "quote": "Remember that I'm saving for a car and want to hit a 720 score by next year."}


@pytest.fixture(autouse=True)
def no_langfuse(monkeypatch):
    """No test reads the developer's Langfuse project, and every test starts with nothing loaded."""
    monkeypatch.setattr(config, "LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setattr(config, "LANGFUSE_SECRET_KEY", "")
    D.forget()


def span(trace, name, start="2026-10-27T10:00:00+00:00", status="OK", **attrs):
    return {"trace_id": trace, "name": name, "start": start, "status": status, "attributes": attrs}


def answer(trace, text="An answer.", session="S2", guardrail="passed", tags=("app",), start="2026-10-27T10:00:00+00:00"):
    """An answer span; by default from the chat app (tagged ``app``), so real use."""
    return span(trace, "creditcoach.answer", start, **{"session.id": session, "answer.guardrail": guardrail,
                                                       "langfuse.trace.output": text, "question": "a question",
                                                       "user.id": "USR-001",
                                                       **({"langfuse.trace.tags": list(tags)} if tags else {})})


def tool(trace, name, ok=True, code=None):
    return span(trace, f"tool.{name}", status="OK" if ok else "ERROR",
                **{"tool.name": name, "tool.ok": ok, **({"tool.code": code} if code else {})})


def traces():
    """Four real answers and one eval answer, covering every measure."""
    return [
        # t1: two tools, one failed; a G2 input trigger; goal from an earlier session, recalled
        answer("t1", "You're aiming for 720 by 2027 to buy a car."), tool("t1", "get_score_history"),
        tool("t1", "get_account_summary", ok=False, code="DATA_UNAVAILABLE"),
        span("t1", "guardrail.input", **{"guardrail.rules": ["G2"]}),
        span("t1", "memory.recall", **{"memory.goal": json.dumps(GOAL)}),
        # t2: reframed for G3; goal stored, but the answer names another target
        answer("t2", "With a target of 750 you would need...", guardrail="reframed"), tool("t2", "get_score_history"),
        span("t2", "guardrail.output", **{"guardrail.rules": ["G3"]}),
        span("t2", "memory.recall", **{"memory.goal": json.dumps(GOAL)}),
        # t3: goal set in this same session: not a recall
        answer("t3", "Saved: 720 by 2027.", session="S1"),
        span("t3", "memory.recall", **{"memory.goal": json.dumps(GOAL)}),
        # t4: blocked for G1 and S1, no goal
        answer("t4", guardrail="blocked", start="2026-10-26T09:00:00+00:00"),
        span("t4", "guardrail.output", **{"guardrail.rules": ["G1", "S1"]}),
        # t5: an eval run, with its own failed tool
        answer("t5", tags=["eval", "eval:baseline"]), tool("t5", "get_score_history", ok=False, code="TIMEOUT"),
        # t6: a trace with no answer (an eval judge call) is left out
        span("t6", "llm.chat"),
    ]


def test_tool_failure_rate_counts_every_call_and_names_the_codes():
    t = D.summarize(D.requests(traces()), "real")["tools"]
    assert (t["calls"], t["failed"], t["answers_hit"]) == (3, 1, 1)
    assert t["rate"] == pytest.approx(1 / 3)
    assert t["per_tool"]["get_account_summary"]["codes"] == {"DATA_UNAVAILABLE": 1}
    assert t["per_tool"]["get_score_history"] == {"calls": 2, "failed": 0, "codes": {}}


def test_a_tool_span_with_error_status_counts_as_failed_even_without_tool_ok():
    rs = D.requests([answer("t"), span("t", "tool.save_goal", status="ERROR", **{"tool.name": "save_goal"})])
    assert D.summarize(rs, "real")["tools"]["failed"] == 1


def test_guardrail_triggers_are_counted_per_rule_with_each_answers_outcome():
    g = D.summarize(D.requests(traces()), "real")["guardrails"]
    assert g["per_rule"] == {"G1": 1, "G2": 1, "G3": 1, "S1": 1}
    assert (g["triggers"], g["answers_hit"]) == (4, 3)
    assert g["outcomes"] == {"passed": 2, "reframed": 1, "blocked": 1}


def test_goal_recall_counts_only_goals_from_an_earlier_session():
    m = D.summarize(D.requests(traces()), "real")["goal"]
    assert (m["answers"], m["recalled"], m["other_target"]) == (2, 1, 1)  # t3 set the goal in the same session
    assert m["rate"] == 0.5


def test_real_use_and_eval_runs_are_kept_apart():
    rs = D.requests(traces())
    assert [D.summarize(rs, k)["answers"] for k in ("real", "eval", "all")] == [4, 1, 5]
    assert D.summarize(rs, "eval")["tools"]["per_tool"]["get_score_history"]["codes"] == {"TIMEOUT": 1}


def test_days_are_listed_newest_first():
    days = D.summarize(D.requests(traces()), "real")["days"]
    assert [(d["day"], d["answers"], d["triggers"], d["goal"]) for d in days] == \
        [("2026-10-27", 3, 2, "1 of 2"), ("2026-10-26", 1, 2, "0 of 0")]


def test_only_the_chat_app_is_real_use_everything_else_is_a_listed_run():
    """29 Oct: the evidence scripts' answers had been counted as real use; only eval-tagged traces were test runs."""
    assert D.run_of({"app"}, "local") is None
    assert D.run_of(set(), "railway") is None                                   # Railway, before the app tag
    assert D.run_of({"eval", "eval:baseline"}, "local") == "eval:baseline"
    assert D.run_of({"script", "script:task32_edge_cases"}, "local") == "script:task32_edge_cases"
    assert D.run_of({"script", "script:task31_dashboard"}, "railway") == "script:task31_dashboard"
    assert D.run_of(set(), "local") == D.UNTAGGED                               # old local traces


def test_eval_and_test_runs_are_listed_by_run():
    rs = D.requests([answer("e1", tags=["eval", "eval:after-fixes"]), answer("e2", tags=["eval", "eval:after-fixes"]),
                     answer("s1", tags=["script", "script:task32_edge_cases"]), answer("o1", tags=None),
                     answer("r1")])
    s = D.summarize(rs, "eval")
    assert s["answers"] == 4 and s["runs"] == {"eval:after-fixes": 2, "script:task32_edge_cases": 1, D.UNTAGGED: 1}
    assert D.summarize(rs, "real")["answers"] == 1 and not D.summarize(rs, "real")["runs"]
    assert "eval:after-fixes 2" in D.html(s, "local trace files", "Last 7 days", "Eval and test runs")



def test_real_use_says_how_many_answers_are_under_the_other_runs():
    """30 Oct: "Real use" over 30 days showed 6 answers, and the older local ones looked lost (they're test runs)."""
    rs = D.requests([answer("e1", tags=["eval", "eval:baseline"]), answer("o1", tags=None), answer("o2", tags=None),
                     answer("r1")])
    real = D.summarize(rs, "real")
    assert real["answers"] == 1 and real["elsewhere"] == {"answers": 3, "untagged": 2}
    page = D.html(real, "local trace files", "Last 30 days", "Real use")
    assert "3 more answers in this period came from eval and test runs, 2 of them" in page
    assert D.summarize(rs, "eval")["elsewhere"] is None
    assert "more answers" not in D.html(D.summarize(rs, "all"), "local trace files", "Last 30 days", "Both")
    assert "more answers" not in D.html(D.summarize(D.requests([answer("r2")]), "real"), "x", "Last 30 days", "Real use")

def observation(s):
    """A local span as Langfuse returns it: attributes under ``metadata``, the answer as ``output``, a level."""
    attrs = dict(s["attributes"])
    out = attrs.pop("langfuse.trace.output", None)
    return {"traceId": s["trace_id"], "name": s["name"], "startTime": s["start"].replace("+00:00", "Z"),
            "level": "ERROR" if s["status"] == "ERROR" else "DEFAULT", "environment": "railway", "output": out,
            "metadata": {"scope.name": "creditcoach", **{f"attributes.{k}": v for k, v in attrs.items()}}}


def test_langfuse_observations_give_the_same_measures_as_the_local_files():
    local = D.summarize(D.requests(traces()), "all")
    remote = D.summarize(D.requests([D._from_observation(observation(s)) for s in traces()]), "all")
    assert {k: v for k, v in remote.items() if k != "where"} == {k: v for k, v in local.items() if k != "where"}
    assert remote["where"] == {"railway": 5}


def test_a_goal_cut_short_by_langfuse_still_gives_its_target_and_session():
    cut = json.dumps(GOAL)[:150]  # Langfuse cuts long metadata strings, here inside "quote"
    assert D._goal(cut) == {"target_score": 720, "session": "S1"}
    assert D._goal("not json") is None and D._goal(None) is None


def test_langfuse_pages_are_followed_until_there_is_no_cursor(monkeypatch):
    calls = []

    def fake_get(path, **q):
        calls.append(q)
        if q.get("name") == "creditcoach.answer" and not q.get("cursor"):
            return {"data": [observation(answer("a"))], "meta": {"cursor": "next"}}
        if q.get("name") == "creditcoach.answer":
            return {"data": [observation(answer("b"))], "meta": {}}
        return {"data": [], "meta": {}}

    monkeypatch.setattr(D, "_langfuse_get", fake_get)
    spans = D.from_langfuse(NOW - timedelta(days=7))
    assert [s["trace_id"] for s in spans] == ["a", "b"]
    assert {q.get("type") for q in calls} == {None, "TOOL"}  # every tool span, whatever its name
    assert all(q["fromStartTime"] == "2026-10-21T12:00:00Z" for q in calls)
    assert "io" in calls[0]["fields"] and all("io" not in q["fields"] for q in calls if q.get("name") != calls[0]["name"])


def write_traces(folder, day, spans):
    with open(folder / f"{day}.jsonl", "a", encoding="utf-8") as f:
        for s in spans:
            f.write(json.dumps(s) + "\n")


def test_local_files_are_read_for_the_period_only(tmp_path):
    write_traces(tmp_path, "2026-10-01", [answer("old", start="2026-10-01T10:00:00+00:00")])
    write_traces(tmp_path, "2026-10-27", [answer("new"), span("new", "context.build")])
    with open(tmp_path / "2026-10-27.jsonl", "a") as f:
        f.write('{"trace_id": "cut sh')  # a line cut short by a crash
    spans = D.from_files(NOW - timedelta(days=7), tmp_path)
    assert [(s["trace_id"], s["name"], s["env"]) for s in spans] == [("new", "creditcoach.answer", "this machine")]


def test_load_falls_back_to_the_local_files_when_langfuse_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setattr(config, "LANGFUSE_SECRET_KEY", "sk")
    monkeypatch.setattr(config, "TRACES_DIR", tmp_path)
    monkeypatch.setattr(D, "from_langfuse", lambda since: 1 / 0)
    write_traces(tmp_path, "2026-10-27", [answer("t")])
    spans, source = D.load(7, now=NOW)
    assert len(spans) == 1 and "Langfuse unreachable" in source


def test_load_keeps_what_it_read_until_refresh(monkeypatch):
    reads = []
    monkeypatch.setattr(D, "from_files", lambda since: reads.append(since) or [])
    D.load(7)
    D.load(7)
    assert len(reads) == 1
    D.forget()
    D.load(7)
    assert len(reads) == 2


def test_the_page_shows_counts_and_never_a_question_answer_or_user():
    page = D.html(D.summarize(D.requests(traces()), "real"), "local trace files", "Last 7 days", "Real use")
    assert "33.3%" in page and "50%" in page and "DATA_UNAVAILABLE ×1" in page
    assert "Never guarantee a score outcome or timeline" in page
    assert not any(secret in page for secret in ("a question", "USR-001", "aiming for 720", "S2"))


def test_an_empty_period_shows_dashes_not_errors():
    page = D.html(D.summarize([], "real"), "local trace files", "Last 24 hours", "Real use")
    assert page.count("–") >= 2 and "No tool calls in this period." in page


def test_view_says_so_when_the_traces_cant_be_read(monkeypatch):
    monkeypatch.setattr(D, "load", lambda days: 1 / 0)
    assert "unavailable" in D.view(7, "real")


def request(username):
    return SimpleNamespace(username=username, session_hash="test")


@pytest.fixture
def signed_up(monkeypatch):
    """creditcoach_user19 is someone who signed up (a login in Neon, not in logins.json)."""
    from creditcoach import auth

    entry = auth.make_entry("USR-002", "a-password")
    monkeypatch.setattr(auth, "signup_logins", lambda reload=False: {"creditcoach_user19": entry})


def test_every_signed_in_user_sees_the_dashboard(monkeypatch, signed_up):
    """Since 2026-10-29: the team's logins and people who signed up alike (user19 on Railway couldn't see it)."""
    monkeypatch.setattr(D, "view", lambda days, traffic: f"dashboard {days} {traffic}")
    for username in ("creditcoach_user1", "creditcoach_user19"):
        tab, page = main.load_dashboard(7, "real", request(username))
        assert tab.visible is True and page == "dashboard 7 real", username
    tab, page = main.load_dashboard(7, "real", request("nobody"))  # a stale session for an unknown login
    assert tab.visible is False and page == ""


def test_the_handlers_check_the_session_too_not_only_the_hidden_tab(monkeypatch, signed_up):
    monkeypatch.setattr(D, "view", lambda days, traffic: "dashboard")
    for handler in (main.dashboard_view, main.refresh_dashboard):
        assert handler(7, "real", request(None)) == main.SIGNED_OUT
        assert handler(7, "real", request("nobody")) == main.SIGNED_OUT
        assert handler(30, "all", request("creditcoach_user19")) == "dashboard"
        assert handler(30, "all", request("creditcoach_user2")) == "dashboard"


def test_the_tab_shows_before_the_traces_are_read(monkeypatch, signed_up):
    """Showing the tab must not wait on Langfuse (it took 4-6 s on a cold cache); the content follows in a .then."""
    monkeypatch.setattr(D, "view", lambda days, traffic: pytest.fail("the tab waited on the traces"))
    tab, page = main.show_dashboard_tab(request("creditcoach_user19"))
    assert tab.visible is True and page == main.DASH_LOADING
    tab, page = main.show_dashboard_tab(request("nobody"))
    assert tab.visible is False and page == ""
