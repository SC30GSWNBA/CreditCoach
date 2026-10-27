"""Task 27: the eval harness. Each expected-answers row is a test case with scorers, run with one command.

No API key needed: answers, the judge and Langfuse are all stubbed. Spans go to memory (``conftest.spans``).

Run:
    uv run pytest tests/test_eval_harness.py -v
"""

import json
from types import SimpleNamespace

import pytest

from creditcoach import config, llm
from creditcoach import observability as obs
from creditcoach.evals import golden, harness, sample_rows

GOOD_JUDGE = {"meets_expected": True, "grounded": 5, "clear": 4, "why": "Uses the tool's figures."}
UTILIZATION = ("Your overall utilization is 37.4%: ₹74,750 ÷ ₹2,00,000 across your cards [1]. Keeping it under 30% "
               "helps.")
SOURCES = '{"overall_utilization_ratio": 0.374, "total_revolving_balance": 74750, "total_revolving_limit": 200000}'


def answer(text=UTILIZATION, model="openai/gpt-5", action="passed", sources=SOURCES, tools=("get_account_summary",)):
    """An object shaped like ``pipeline.Answer``, as much as the harness and the chat UI read."""
    ns = SimpleNamespace
    return ns(text=text, model=model, sources=sources, question="q", user_id="USR-001", retrieval_seconds=0.1,
              generation_seconds=1.0, cache={"status": "off", "events": []}, trace_id=None,
              guardrail=ns(action=action, reviewed=False, remaining=[], findings=[], rules=[],
                           screen=ns(findings=[]), draft=None),
              passages=[ns(id="factor-credit-utilization#00", category="scoring_factor", score=0.7, title="Utilization",
                           text="Utilization\n\nKeep it low.", metadata={"source": "corpus/x.md"})],
              tool_calls=[ns(tool=t, ok=True, code=None, arguments={}, result={}, seconds=0.1) for t in tools])


def sample_record(qid=2, a=None, judge=None, **extra):
    q = golden.by_id()[qid]
    a = a or answer()
    return {**harness._base(q), "session": 2, "seconds": 7.0, "error": None, "trace_id": "ab" * 16, "reply": a.text,
            "answer": a.text, "model": a.model, "guardrail": a.guardrail.action,
            "tools": [{"tool": c.tool, "ok": True, "code": None} for c in a.tool_calls], "passages": [],
            "snapshot": sample_rows.snapshot(a), "goal_before": None, "goal_after": None,
            "judge": judge or dict(GOOD_JUDGE), **extra}


def scored(*recs):
    run = {"model": "openai/gpt-5", "records": list(recs)}
    harness.score_run(run)
    return run["records"]


def by_name(rec):
    return {s["name"]: s for s in rec["scores"]}


# ---- Scorers ----

def test_a_row_that_meets_every_expectation_passes():
    [r] = scored(sample_record())
    assert r["pass"] and [s["name"] for s in r["scores"]] == ["expected", "judge", "run"]
    assert by_name(r)["expected"]["value"] == 1.0 and by_name(r)["judge"]["value"] == 0.9


def test_a_missing_figure_fails_the_expected_scorer_and_says_which():
    [r] = scored(sample_record(a=answer(text="Your utilization is high; pay down the card [1].")))
    s = by_name(r)["expected"]
    assert not r["pass"] and not s["passed"] and "37.4%" in s["detail"] and 0 < s["value"] < 1


def test_an_invented_figure_fails():
    [r] = scored(sample_record(a=answer(text=UTILIZATION + " Your score will be 742 soon.")))
    assert not r["pass"] and "untraced: 742" in by_name(r)["expected"]["detail"]


@pytest.mark.parametrize("judge, why", [
    ({**GOOD_JUDGE, "meets_expected": False}, "meets expected: no"),
    ({**GOOD_JUDGE, "grounded": 3}, "grounded 3/5"),
    ({**GOOD_JUDGE, "clear": 2}, "clear 2/5"),
    ({"error": "ValueError: bad json"}, "judge failed"),
])
def test_the_judge_fails_a_case_below_its_bar(judge, why):
    [r] = scored(sample_record(judge=judge))
    assert not r["pass"] and not by_name(r)["judge"]["passed"] and why in by_name(r)["judge"]["detail"]


@pytest.mark.parametrize("a, error, why", [
    (answer(model="openai/fallback"), None, "not openai/gpt-5"),
    (answer(action="blocked"), None, "blocked"),
    (answer(), "Traceback ...\nTimeoutError: slow", "crashed: TimeoutError: slow"),
])
def test_the_run_scorer_fails_a_crash_the_fallback_model_or_a_block(a, error, why):
    [r] = scored(sample_record(a=a, error=error))
    assert not r["pass"] and why in by_name(r)["run"]["detail"]


def test_query_5_later_session_check_is_settled_by_query_3():
    five = sample_record(5, a=answer(text="Saved: 720 for your car by 2027.", tools=("save_goal",)),
                         goal_after=[720, "2027", "saving for a car"])
    three = sample_record(3, a=answer(text="Your goal is 720 by 2027."), goal_before=[720, "2027", "car"],
                          goal_after=[720, "2027", "car"])
    recs = {r["id"]: r for r in scored(five, three)}
    last = recs[5]["criteria"][-1]
    assert last["held"] == recs[3]["criteria"][0]["held"] is True and last["detail"].startswith("session 2, query 3")


def test_additional_queries_are_scored_with_the_golden_checks_and_figure_tracing():
    q = golden.by_id()[26]  # "What's my utilization on each card?" style §4 query
    rec = {**harness._base(q), "mode": "tools", "seconds": 5.0, "error": None, "trace_id": None, "answer": "No idea.",
           "model": "openai/gpt-5", "guardrail": "passed", "tool_calls": [], "tools": [], "passages": [],
           "passages_full": [], "judge": dict(GOOD_JUDGE)}
    [r] = scored(rec)
    assert [s["name"] for s in r["scores"]] == ["expected", "figures", "judge", "run"]
    assert not r["pass"] and not by_name(r)["expected"]["passed"]


def test_the_judge_sees_the_users_profile_for_additional_queries():
    """Found by the Task 28 baseline: #24's judge called the user's name and emergency fund unsupported, because
    the §4 judge saw the passages and tool results but not the profile they come from."""
    q = golden.by_id()[24]
    rec = {**harness._base(q), "query": q.query, "passages_full": [], "tool_calls": []}
    assert "Manish" in harness.sources(rec) and "More than 6 months" in harness.sources(rec)


def test_the_judge_sees_a_goal_the_harness_stored_first():
    """Found in Task 30: #39's judge called the stored 720 and 2027 invented, because it couldn't see the memory."""
    q = golden.by_id()[39]
    rec = {**harness._base(q), "passages_full": [], "tool_calls": [], "seeded_goal": harness.CAR_720[0]}
    assert '"target_score": 720' in harness.sources(rec) and "Stored goal" in harness.sources(rec)


def test_rejudge_judges_saved_answers_again_without_new_answers(monkeypatch, tmp_path):
    monkeypatch.setattr(harness, "WEEK4", tmp_path)
    run = {"created": "2026-10-26T10:00:00", "label": "unit", "scope": "sample", "model": "openai/gpt-5",
           "judge_model": "m", "minutes": 1.0, "records": [sample_record(judge={**GOOD_JUDGE, "grounded": 3})]}
    harness.save(run, harness.paths("unit")[1])
    monkeypatch.setattr(harness, "judge", lambda rec: dict(GOOD_JUDGE))
    monkeypatch.setattr(harness, "push_scores", lambda recs: len(recs))
    assert not harness.rescore("unit")["records"][0]["pass"]  # --rescore keeps the saved verdict
    result = harness.rescore("unit", rejudge=True)
    assert result["records"][0]["pass"] and result["rejudged"] and result["langfuse_cases"] == 1


def test_a_query_that_assumes_a_stored_goal_gets_it_in_its_own_memory(monkeypatch, tmp_path):
    """Task 30: the §4 memory queries ran with no memory (Task 29: 5 of the 14 failures). Each now gets the goal its
    requirements.md row assumes, stored in a first session, and nothing else from earlier cases."""
    from creditcoach.agent import pipeline
    from creditcoach.memory import store

    monkeypatch.setattr(config, "MEMORY_DIR", tmp_path / "memory")
    store.set_goal(store.start_session("USR-001", source="eval"), {"target_score": 750, "target_date": None,
                                                                    "purpose": "x"}, "an earlier case changed it")
    seen = {}

    def fake_answer(question, user_id, session=None, **kw):
        seen.update(goal=store.load(user_id).goal, session=session)
        return answer(tools=())
    monkeypatch.setattr(pipeline, "answer", fake_answer)
    rec = harness.run_with_stored_goal(golden.by_id()[38], "unit")
    assert (seen["goal"].target_score, seen["goal"].target_date) == (720, "2027")  # #5's goal, not the 750 left over
    assert seen["session"] is not None and rec["seeded_goal"]["target_score"] == 720 and rec["error"] is None
    assert not harness.unset({**harness._base(golden.by_id()[38]), "seeded_goal": rec["seeded_goal"]})
    assert harness.unset(harness._base(golden.by_id()[47]))  # still needs a follow-up turn this run doesn't set up


def test_compare_keeps_measurement_changes_out_of_the_like_for_like_score(monkeypatch, tmp_path):
    monkeypatch.setattr(harness, "WEEK4", tmp_path)
    monkeypatch.setattr(harness, "MEASUREMENT_CHANGES", {38: "the goal its row assumes is now stored first"})
    bad = {**GOOD_JUDGE, "meets_expected": False}

    def run(label, judge):  # one §3 row (unchanged measurement), and the same scored as #38 (goal now stored first)
        r = {"created": "2026-10-27T10:00:00", "label": label, "scope": "all", "model": "openai/gpt-5",
             "judge_model": "m", "minutes": 1.0, "records": [sample_record(2, judge=judge)]}
        harness.score_run(r)
        r["records"].append({**r["records"][0], "id": 38, "label": "§4 #38"})
        harness.save(r, harness.paths(label)[1])
    run("before", bad)
    run("after", GOOD_JUDGE)
    monkeypatch.setattr(harness, "score_run", lambda run: None)  # the re-score of "before" is tested elsewhere
    text = harness.compare("before", "after").read_text()
    assert "| **Like for like** (measurement unchanged) | 1 | 0 (0%) | 1 (100%) | +1 |" in text
    assert "| Measurement changed (see below) | 1 | 0 (0%) | 1 (100%) | +1 |" in text
    assert "| **All** | 2 | 0 (0%) | 2 (100%) | +2 |" in text and "the goal its row assumes is now stored first" in text


# ---- Judge ----

def test_the_judge_uses_the_small_model_and_reads_json_from_its_reply(monkeypatch):
    seen = {}

    def fake_chat(messages, model=None, effort=None):
        seen.update(model=model, prompt=messages[1]["content"])
        return 'Verdict:\n{"meets_expected": true, "grounded": 5, "clear": 4, "why": "ok"}', model
    monkeypatch.setattr(llm, "chat", fake_chat)
    j = harness.judge(sample_record())
    assert j["meets_expected"] and j["grounded"] == 5 and seen["model"] == config.SMALL_MODEL
    assert "EXPECTED BEHAVIOR:\nCalls the account-summary tool" in seen["prompt"] and "74750" in seen["prompt"]


def test_a_broken_judge_reply_is_recorded_not_raised(monkeypatch):
    monkeypatch.setattr(llm, "chat", lambda messages, model=None, effort=None: ("I think it's fine", model))
    assert "error" in harness.judge(sample_record())
    assert harness.judge({**sample_record(), "answer": ""}) == {"error": "no answer to judge"}


# ---- Langfuse ----

def test_scores_are_attached_to_each_case_trace(monkeypatch):
    sent = []
    monkeypatch.setattr(obs, "score", lambda trace_id, name, value, comment=None: sent.append((name, value)) or True)
    [r] = scored(sample_record())
    assert harness.push_scores([r]) == 1
    assert sent == [("eval.pass", True), ("eval.expected", 1.0), ("eval.judge.grounded", 5), ("eval.judge.clear", 4)]


def test_score_posts_to_langfuse_only_with_keys(monkeypatch):
    calls = []

    class Reply:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: calls.append(req) or Reply())
    monkeypatch.setattr(config, "LANGFUSE_PUBLIC_KEY", "")
    assert obs.score("ab" * 16, "eval.pass", True) is False and not calls
    monkeypatch.setattr(config, "LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setattr(config, "LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setattr(config, "LANGFUSE_HOST", "https://lf.example")
    assert obs.score("ab" * 16, "eval.pass", True, "every scorer passed") is True
    [req] = calls
    assert req.full_url == "https://lf.example/api/public/scores" and req.get_header("Authorization").startswith("Basic ")
    assert json.loads(req.data) == {"id": "ab" * 16 + "-eval.pass", "traceId": "ab" * 16, "name": "eval.pass", "value": 1.0, "dataType": "BOOLEAN",
                                    "comment": "every scorer passed"}


def test_langfuse_status_names_the_region_when_the_keys_are_refused(monkeypatch):
    """Found on Railway: without LANGFUSE_HOST the EU host refused Japan-region keys and every trace was dropped."""
    import urllib.error
    import urllib.request

    def refused(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)
    monkeypatch.setattr(urllib.request, "urlopen", refused)
    monkeypatch.setattr(config, "LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setattr(config, "LANGFUSE_SECRET_KEY", "sk")
    accepted, message = obs.langfuse_status()
    assert accepted is False and "401" in message and "LANGFUSE_HOST" in message
    monkeypatch.setattr(config, "LANGFUSE_PUBLIC_KEY", "")
    assert obs.langfuse_status() == (None, "no Langfuse keys set")


def test_a_langfuse_error_never_stops_the_run(monkeypatch):
    import urllib.request

    def down(req, timeout):
        raise OSError("connection refused")
    monkeypatch.setattr(urllib.request, "urlopen", down)
    monkeypatch.setattr(config, "LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setattr(config, "LANGFUSE_SECRET_KEY", "sk")
    assert obs.score("ab" * 16, "eval.judge.clear", 4) is False


# ---- Report ----

def test_report_shows_the_score_each_case_and_tester_verdicts(tmp_path):
    good = sample_record()
    bad = sample_record(1, a=answer(text="It dropped."))
    good["human"] = [{"tester": "T1", "verdict": "helpful", "feedback": "Clear numbers."}]
    result = {"created": "2026-10-26T10:00:00", "label": "unit", "scope": "sample", "model": "openai/gpt-5",
              "judge_model": "m", "minutes": 1.0, "langfuse_cases": 0, "records": [bad, good]}
    harness.score_run(result)
    report = tmp_path / "eval-unit.md"
    harness.write_report(result, report, tmp_path / "eval-unit.json")
    text = report.read_text()
    assert "**Score: 1 of 2 cases pass (50%)**" in text and "| T1 | helpful | Clear numbers. |" in text
    assert "### Case 1" in text and "❌ Fail" in text and "✅ Pass" in text


def test_labels_are_safe_file_names():
    assert harness.paths("baseline")[1].name == "eval-baseline.json"
    with pytest.raises(ValueError):
        harness.paths("../oops")


# ---- The run, end to end through the chat functions ----

def test_sample_rows_run_in_two_sessions_each_case_one_trace(monkeypatch, tmp_path, spans):
    from creditcoach.app import main as app
    from creditcoach.memory import dream

    monkeypatch.setattr(config, "MEMORY_DIR", tmp_path / "memory")  # restored after the test
    monkeypatch.setattr(app, "_sessions", {})
    monkeypatch.setattr(dream, "dream", lambda user_id, exclude_session=None: {})
    inner = {}

    def fake_answer(question, user_id, session=None, **kw):
        with obs.span("creditcoach.answer"):  # as the pipeline does, on the chat's worker thread
            inner[question] = obs.trace_id()
        return answer()
    monkeypatch.setattr(app, "answer", fake_answer)
    recs = harness.run_sample_rows("unit")
    assert [(r["id"], r["session"]) for r in recs] == [(5, 1), (1, 2), (2, 2), (3, 2), (4, 2), (6, 2)]
    assert [r["error"] for r in recs] == [None] * 6 and all(r["answer"] == UTILIZATION for r in recs)
    assert len({r["trace_id"] for r in recs}) == 6
    assert all(inner[r["query"]] == r["trace_id"] for r in recs)  # the answer is inside its case's trace
    case = next(s for s in spans.get_finished_spans() if s.name == "eval.case")
    assert case.attributes["langfuse.trace.tags"] == ("eval", "eval:unit")
    assert app.answer is fake_answer  # restored
