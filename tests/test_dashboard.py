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


# ---- Cost and speed (2026-11-01) ----

def costed(trace, model="anthropic/claude-sonnet-5.5", ms=10_000, tags=("app",), cost=0.02, check=0.0003,
           rewrite=0.0, day="2026-10-27"):
    """One answer with its spans as the pipeline leaves them: the answer model under ``agent``, the output check
    (and any rewrite) under ``guardrail.output``, a tool call and retrieval; plus an eval judge's call, which isn't
    the answer's."""
    start = f"{day}T10:00:00+00:00"

    def s(sid, name, parent, ms_, **attrs):
        return {**span(trace, name, start, **attrs), "span_id": f"{trace}-{sid}",
                "parent_id": parent and f"{trace}-{parent}", "ms": ms_}

    def call(sid, parent, ms_, model_, cost_, tokens):
        return s(sid, "llm.chat", parent, ms_, **{"gen_ai.response.model": model_, "gen_ai.usage.cost": cost_,
                                                  "gen_ai.usage.input_tokens": tokens[0],
                                                  "gen_ai.usage.output_tokens": tokens[1]})

    spans_ = [{**answer(trace, tags=tags, start=start), "span_id": f"{trace}-a", "parent_id": None, "ms": ms},
              s("i", "guardrail.input", "a", 20), s("r", "retrieval", "a", 600), s("g", "agent", "a", 7_000),
              call("m", "g", 6_000, model, cost, (9_000, 600)),
              {**tool(trace, "get_score_history"), "span_id": f"{trace}-t", "parent_id": f"{trace}-g", "ms": 800},
              s("o", "guardrail.output", "a", 1_500), call("c", "o", 1_200, config.SMALL_MODEL, check, (2_000, 50)),
              call("j", None, 3_000, config.SMALL_MODEL, 0.5, (1, 1))]  # the judge: not under the answer
    spans_[0]["attributes"]["answer.model"] = model
    if rewrite:
        spans_.append(call("w", "o", 2_000, model, rewrite, (9_000, 500)))
    return spans_


def cost_traces():
    return [*costed("c1"), *costed("c2", ms=20_000, cost=0.03, rewrite=0.01, day="2026-10-28"),
            *costed("c3", model="openai/gpt-5", ms=16_000, cost=0.01),
            *costed("c4", tags=["eval", "eval:baseline"], cost=0.5)]


def test_each_model_call_is_costed_by_the_step_it_sits_under_and_judges_are_left_out():
    rs = {r["trace_id"]: r for r in D.requests(cost_traces())}
    assert rs["c1"]["cost"] == {"answer": 0.02, "check": 0.0003, "rewrite": 0.0}
    assert rs["c2"]["cost"] == {"answer": 0.03, "check": 0.0003, "rewrite": 0.01}
    assert rs["c1"]["prompt_tokens"] == 11_000 and rs["c1"]["completion_tokens"] == 650
    assert rs["c1"]["seconds"] == 10 and rs["c1"]["model"] == "anthropic/claude-sonnet-5.5"
    steps = rs["c1"]["steps"]
    assert (steps["model"], steps["check"], steps["tools"], steps["retrieval"]) == (6, 1.2, .8, .6)
    assert steps["other"] == pytest.approx(10 - 6 - 1.2 - .8 - .6 - .02)


def test_cost_and_speed_are_summed_per_model_and_day_for_the_traffic_picked():
    c = D.summarize(D.requests(cost_traces()), "real")["cost"]
    assert c["answers"] == 3 and c["spend"] == pytest.approx(0.02 + 0.04 + 0.01 + 3 * 0.0003)
    assert c["p50"] == 16 and c["p95"] == 20  # nearest rank
    assert list(c["models"]) == ["anthropic/claude-sonnet-5.5", "openai/gpt-5"]  # most answers first
    assert c["models"]["anthropic/claude-sonnet-5.5"]["answers"] == 2
    assert c["days"]["2026-10-28"]["by_model"] == {"anthropic/claude-sonnet-5.5": pytest.approx(0.04),
                                                   "check": pytest.approx(0.0003)}
    assert c["split"]["rewrite"] == pytest.approx(0.01) and len(c["points"]) == 3
    assert D.summarize(D.requests(cost_traces()), "eval")["cost"]["spend"] == pytest.approx(0.5003)


def test_langfuse_observations_give_the_same_cost_and_speed_as_the_local_files():
    def observed(s):
        o = observation(s)
        return {**o, "id": s["span_id"], "parentObservationId": s["parent_id"], "latency": s["ms"] / 1000}

    local = D.summarize(D.requests(cost_traces()), "all")["cost"]
    remote = D.summarize(D.requests([D._from_observation(observed(s)) for s in cost_traces()]), "all")["cost"]
    assert remote["spend"] == pytest.approx(local["spend"]) and remote["p50"] == pytest.approx(local["p50"])
    assert remote["steps"] == pytest.approx(local["steps"])


def test_percentiles_are_by_nearest_rank_as_the_eval_reports_give_them():
    assert D.rank(list(range(1, 51)), .9) == 45 and D.rank([3.0], .95) == 3.0 and D.rank([], .5) is None


def test_model_ids_are_named_as_people_say_them():
    assert D.model_name("anthropic/claude-sonnet-5.5") == "Claude Sonnet 5.5"
    assert D.model_name("openai/gpt-5.6-terra") == "GPT-5.6 Terra"
    assert D.model_name("openai/gpt-5") == "GPT-5" and D.model_name("") == "No model call"


def test_the_cost_view_has_every_part_and_never_a_question_answer_or_user(monkeypatch):
    monkeypatch.setattr(D, "load", lambda days: (cost_traces(), "local trace files"))
    parts = D.cost_view(7, "real")
    assert set(parts) == {*D.COST_PARTS, "costs"} and all(parts[k] is not None for k in D.COST_PARTS)
    page = "".join(v for v in parts.values() if isinstance(v, str))
    assert "Models compared" in page and "Claude Sonnet 5.5" in page
    assert not any(secret in page for secret in ("a question", "USR-001", "An answer."))
    assert {t.name for t in parts["scatter"].data if t.showlegend is not False} == {"Claude Sonnet 5.5 (2)",
                                                                                     "GPT-5 (1)"}


def test_the_cost_view_says_so_when_the_traces_cant_be_read(monkeypatch):
    monkeypatch.setattr(D, "load", lambda days: 1 / 0)
    parts = D.cost_view(7, "real")
    assert "unavailable" in parts["top"] and parts["scatter"] is None


def test_the_model_comparison_ships_with_the_app_and_names_the_model_that_meets_the_target(monkeypatch):
    cmp = D.comparison()
    assert cmp and cmp["target_seconds"] == 15 and len(cmp["rows"]) >= 5
    assert all(r["cases"] == 50 and r["per_answer"] for r in cmp["rows"])
    monkeypatch.setattr(config, "CHAT_MODEL", "anthropic/claude-sonnet-5.5")
    page = D.quality_html(cmp)
    assert "Claude Sonnet 5.5 is the only model with the top score (43/50)" in page
    assert page.count("Current") == 1 and "over target" in page
    assert "isn't available" in D.quality_html(None)


def test_the_cost_view_is_built_only_when_picked_and_only_for_a_signed_in_user(monkeypatch, signed_up):
    monkeypatch.setattr(D, "cost_view", lambda days, traffic: {k: k for k in D.COST_PARTS} | {"costs": None})
    shown = main.cost_dashboard(7, "real", "cost", request("creditcoach_user19"))
    assert shown[:len(D.COST_PARTS)] == D.COST_PARTS and len(shown) == len(D.COST_PARTS) + 2
    assert main.cost_dashboard(7, "real", "cost", request("nobody"))[0] == main.SIGNED_OUT
    skipped = main.cost_dashboard(7, "real", "quality", request("creditcoach_user19"))
    assert len(skipped) == len(D.COST_PARTS) + 2 and not any(isinstance(p, str) for p in skipped)
    quality, cost = main.dashboard_switch("cost")
    assert quality["visible"] is False and cost["visible"] is True


# ---------------------------------------------------------------- the chart's figures follow the ticked models

SONNET, GPT5 = "anthropic/claude-sonnet-5.5", "openai/gpt-5"


def real_costs():
    """Sonnet: 10 s and 20 s; GPT-5: 16 s. Medians of the models are 15 and 16, but of all three answers, 16."""
    rs = D.requests(cost_traces())
    return D.summarize(rs, "real")["cost"], [r for r in rs if not r["eval"]]


@pytest.mark.parametrize("shown", [[SONNET], [GPT5], [SONNET, GPT5]])
def test_a_choice_of_models_gets_the_figures_of_exactly_those_answers(shown):
    c, rs = real_costs()
    truth = D._speed([r for r in rs if r["model"] in shown])  # worked out afresh from the answers themselves
    got = D.pick(c, shown)
    assert got["answers"] == truth["answers"]
    assert got["per_answer"] == pytest.approx(truth["per_answer"]) and got["p50"] == truth["p50"]


def test_one_model_gets_its_row_in_the_models_compared_table_and_every_model_the_tiles():
    c, _ = real_costs()
    for model, row in c["models"].items():
        got = D.pick(c, [model])
        assert (got["answers"], got["per_answer"], got["p50"]) == (row["answers"], row["per_answer"], row["p50"])
    every = D.pick(c)
    assert every["answers"] == c["answers"] and every["p50"] == c["p50"] == 16  # not 15.5, the medians' mean
    assert every["per_answer"] == pytest.approx(c["per_answer"])


def test_the_chart_draws_only_the_ticked_models_with_their_count_median_and_average():
    c, _ = real_costs()
    fig = D.scatter_figure(c, [GPT5])
    gpt5 = c["models"][GPT5]
    assert {t.legendgroup for t in fig.data} == {GPT5}
    texts = [a.text for a in fig.layout.annotations]
    assert "<b>1 of 3 answers</b>" in texts
    assert f"median {D._secs(gpt5['p50'])}" in texts and f"average {D._usd(gpt5['per_answer'])}" in texts
    assert any(sh.x0 == sh.x1 == gpt5["p50"] for sh in fig.layout.shapes)  # the median line
    assert any(sh.y0 == sh.y1 == gpt5["per_answer"] for sh in fig.layout.shapes)  # the average line
    assert fig.layout.legend.itemclick is False and fig.layout.legend.itemdoubleclick is False
    assert "<b>3 answers</b>" in [a.text for a in D.scatter_figure(c).layout.annotations]


def test_with_no_model_ticked_the_chart_says_to_tick_one():
    c, _ = real_costs()
    fig = D.scatter_figure(c, [])
    assert not fig.data and not fig.layout.shapes
    assert [a.text for a in fig.layout.annotations] == ["<b>Tick a model to see its answers</b>"]
    assert fig.layout.xaxis.visible is False and fig.layout.yaxis.visible is False


def test_the_tick_boxes_name_each_model_with_its_answers_and_answers_with_no_model_call_too():
    c, _ = real_costs()
    assert D.model_choices(c) == [("Claude Sonnet 5.5 (2)", SONNET), ("GPT-5 (1)", GPT5)]
    c["models"][""], c["times"][""] = {**c["models"][GPT5], "answers": 4, "spend": 0.0}, [1.0, 2.0, 3.0, 4.0]
    assert D.model_choices(c)[-1] == ("No model call (4)", D.NO_MODEL)
    assert D.pick(c, [D.NO_MODEL]) == {"models": {"": c["models"][""]}, "answers": 4, "spend": 0.0,
                                       "per_answer": 0.0, "p50": 2.5}


def test_the_chart_is_redrawn_from_the_view_s_own_figures_and_only_for_a_signed_in_user(signed_up):
    c, _ = real_costs()
    fig = main.redraw_cost_scatter([SONNET], c, request("creditcoach_user19"))
    assert {t.legendgroup for t in fig.data} == {SONNET}
    assert not hasattr(main.redraw_cost_scatter([SONNET], c, request("nobody")), "data")  # gr.skip(), no figure
    assert not hasattr(main.redraw_cost_scatter([SONNET], None, request("creditcoach_user19")), "data")


def test_the_page_builds_with_the_tick_boxes_wired_to_the_chart():
    demo = main.build()  # fails if a handler's name is shadowed by a component's, as it once was
    assert any(getattr(b, "label", None) == "Models shown" for b in demo.blocks.values())
