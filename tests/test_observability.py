"""Task 26: every event of one request (retrieval, tool calls, guardrail triggers, tool failures, model calls,
cache lookups) is recorded under a single trace ID.

No API key needed: the model is scripted, retrieval is stubbed, and the account tool is made to time out through
the MCP host's real timeout path. Spans go to memory (``conftest.spans``).

Run:
    uv run pytest tests/test_observability.py -v
"""

import json
from types import SimpleNamespace

import pytest

from creditcoach import cache, config, llm
from creditcoach import observability as obs
from creditcoach.agent import pipeline
from creditcoach.evals.live import TimingOutAccounts
from creditcoach.guardrails import checks
from creditcoach.rag.retrieve import Result

PAYDAY = "Should I take out this payday loan to pay off my credit card?"
ANSWER = ("I wouldn't take that payday loan: the fees are very high [1]. Your score is 650; a lower-cost option is "
          "to pay the card's minimum and talk to your bank about a repayment plan [1].")


def passage(id_, category):
    return Result(rank=1, id=id_, score=0.71, title="Payday loans", category=category,
                  text="Payday loans\n\nPayday loans charge very high fees.", metadata={"source": "corpus/x.md"})


@pytest.fixture
def request_with_a_failing_tool(monkeypatch):
    """One signed-in payday-loan question, with the account summary timing out and a scripted model."""
    monkeypatch.setattr(pipeline, "McpHost", TimingOutAccounts)
    monkeypatch.setattr(pipeline, "retrieve", lambda q, k=3, where=None: [
        passage("payday-loans#00" if where else "why-scores-drop#01", "product_risk" if where else "scoring_factor")])
    monkeypatch.setattr(pipeline, "chat_with_tools",
                        lambda messages, tools, model=None: (SimpleNamespace(content=ANSWER, tool_calls=None), "m"))
    monkeypatch.setattr(checks, "model_review", lambda question, answer, projection, product: [])
    return pipeline.answer(PAYDAY, user_id="USR-001")


def by_name(spans):
    return {s.name: s for s in spans}


def test_every_event_of_one_request_shares_its_trace_id(request_with_a_failing_tool, spans):
    a = request_with_a_failing_tool
    finished = spans.get_finished_spans()
    assert a.trace_id and len(a.trace_id) == 32
    assert {format(s.context.trace_id, "032x") for s in finished} == {a.trace_id}  # one trace, nothing outside it
    names = by_name(finished)
    for name in ("creditcoach.answer", "guardrail.input", "retrieval", "agent", "tool.get_score_history",
                 "tool.get_account_summary", "guardrail.output"):
        assert name in names, name
    root = names["creditcoach.answer"]
    assert root.parent is None and all(s.parent is not None for s in finished if s is not root)
    # Langfuse filters by user from each span, so every span carries the user, not just the root
    assert all(s.attributes.get("langfuse.user.id") == "USR-001" for s in finished)


def test_the_spans_record_retrieval_tool_failure_and_guardrail_trigger(request_with_a_failing_tool, spans):
    names = by_name(spans.get_finished_spans())

    retrieval = names["retrieval"].attributes
    assert list(retrieval["retrieval.passages"]) == ["why-scores-drop#01", "payday-loans#00"]
    assert retrieval["retrieval.risk_added"] is True

    ok, failed = names["tool.get_score_history"], names["tool.get_account_summary"]
    assert ok.status.is_ok and ok.attributes["tool.ok"] is True
    assert failed.status.status_code.name == "ERROR" and failed.attributes["tool.code"] == "DATA_UNAVAILABLE"
    assert failed.attributes["tool.attempts"] == 2  # retryable, so retried once
    assert [e.name for e in failed.events] == ["tool.retry", "tool.failure"]
    assert failed.events[-1].attributes["code"] == "DATA_UNAVAILABLE"

    triggers = [e for e in names["guardrail.input"].events if e.name == "guardrail.trigger"]
    assert [(e.attributes["rule"], e.attributes["stage"]) for e in triggers] == [("G2", "input")]
    assert names["guardrail.output"].attributes["guardrail.action"] == "passed"

    root = names["creditcoach.answer"].attributes
    assert root["user.id"] == "USR-001" and root["answer.tool_failures"] == 1
    assert root["langfuse.trace.input"] == PAYDAY and root["langfuse.trace.output"] == ANSWER


def test_a_masked_identifier_never_reaches_a_span(monkeypatch, spans):
    monkeypatch.setattr(pipeline, "retrieve", lambda q, k=3, where=None: [])
    monkeypatch.setattr(pipeline, "chat", lambda messages, model=None, effort=None: ("A general answer.", "m"))
    pipeline.answer("My PAN is ABCDE1234F. What is credit utilization?")
    dumped = json.dumps([obs.as_dict(s) for s in spans.get_finished_spans()])
    assert "ABCDE1234F" not in dumped and "[PAN removed]" in dumped
    assert '"S3"' in dumped  # the masking itself is recorded as a guardrail trigger


def test_cache_lookups_are_events_on_the_current_span(monkeypatch, spans):
    monkeypatch.setattr(config, "CACHE", "on")
    cache.use(None)
    try:
        with obs.span("creditcoach.answer"):
            with obs.span("retrieval"):
                cache.get("retrieval", cache.key("retrieval", "q"))
    finally:
        cache.use(None)
    retrieval = by_name(spans.get_finished_spans())["retrieval"]
    assert [(e.name, e.attributes["layer"], e.attributes["result"]) for e in retrieval.events] == [
        ("cache", "retrieval", "miss")]


class FakeClient:
    def __init__(self, failing=()):
        self.failing = set(failing)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        if kwargs["model"] in self.failing:
            raise RuntimeError("402 This request requires more credits")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=None))],
                               usage=SimpleNamespace(prompt_tokens=120, completion_tokens=30, cost=0.0042))


def test_a_model_call_is_a_generation_with_tokens_cost_and_any_fallback(monkeypatch, spans):
    monkeypatch.setattr(llm, "get_client", lambda: FakeClient(failing={config.CHAT_MODEL}))
    llm.chat([{"role": "user", "content": "hi"}])
    (s,) = spans.get_finished_spans()
    assert s.name == "llm.chat" and s.attributes["langfuse.observation.type"] == "generation"
    assert s.attributes["gen_ai.request.model"] == config.CHAT_MODEL
    assert s.attributes["gen_ai.response.model"] == config.FALLBACK_MODEL and s.attributes["llm.fallback"] is True
    assert (s.attributes["gen_ai.usage.input_tokens"], s.attributes["gen_ai.usage.output_tokens"]) == (120, 30)
    assert s.attributes["gen_ai.usage.cost"] == 0.0042
    assert [e.name for e in s.events] == ["llm.fallback"]


def test_the_file_exporter_writes_one_line_per_span_and_load_reads_a_trace_back(tmp_path):
    obs.configure([obs.FileExporter(tmp_path)])
    with obs.span("creditcoach.answer", **{"user.id": "USR-001"}):
        with obs.span("retrieval", passages=["a", "b"]):
            obs.event("cache", layer="retrieval", result="hit")
        first = obs.trace_id()
    with obs.span("creditcoach.answer"):
        pass
    spans = obs.load(first, tmp_path)
    assert [s["name"] for s in spans] == ["retrieval", "creditcoach.answer"]
    assert spans[0]["parent_id"] == spans[1]["span_id"] and spans[0]["attributes"]["passages"] == ["a", "b"]
    assert spans[0]["events"][0]["attributes"] == {"layer": "retrieval", "result": "hit"}


def test_attribute_values_are_made_safe_for_opentelemetry():
    long = "x" * (obs.MAX_TEXT + 10)
    attrs = obs.attributes(a=None, b={"k": 1}, c=long, d=[1, 2], e=[], f=True)
    assert "a" not in attrs and attrs["b"] == '{"k": 1}' and attrs["d"] == [1, 2] and attrs["e"] == "[]"
    assert attrs["c"].endswith("[10 more characters]") and attrs["f"] is True


def test_recording_outside_a_trace_is_a_no_op():
    obs.event("cache", layer="tool")
    obs.annotate(x=1)
    obs.fail("nothing to fail")
    assert obs.trace_id() is None


def test_langfuse_base_url_is_read_when_langfuse_host_is_not_set(monkeypatch):
    """Langfuse's setup snippet names it LANGFUSE_BASE_URL; pasting that once sent the keys to the wrong region."""
    import importlib

    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://jp.cloud.langfuse.com")
    assert importlib.reload(config).LANGFUSE_HOST == "https://jp.cloud.langfuse.com"
    monkeypatch.setenv("LANGFUSE_HOST", "https://us.cloud.langfuse.com")  # LANGFUSE_HOST wins when both are set
    assert importlib.reload(config).LANGFUSE_HOST == "https://us.cloud.langfuse.com"
    monkeypatch.undo()
    importlib.reload(config)


def test_every_new_trace_says_which_process_made_it(spans, monkeypatch):
    """The dashboard tells real use (the chat app) from scripts and eval runs by these tags (2026-10-29)."""
    monkeypatch.setattr(obs, "_run", [])
    monkeypatch.setattr("sys.argv", ["/x/scripts/task32_edge_cases.py"])
    with obs.span("creditcoach.answer"):
        with obs.span("retrieval"):
            pass
    monkeypatch.setattr("sys.argv", ["/x/creditcoach/evals/__main__.py"])
    with obs.span("eval.case", root=True, carry={"langfuse.trace.tags": ["eval", "eval:baseline"]}):
        pass                                                                   # its own tags win
    obs.set_run("app")
    with obs.span("creditcoach.answer"):
        pass
    tags = [(s.name, tuple(s.attributes["langfuse.trace.tags"])) for s in spans.get_finished_spans()]
    assert tags == [("retrieval", ("script", "script:task32_edge_cases")),
                    ("creditcoach.answer", ("script", "script:task32_edge_cases")),
                    ("eval.case", ("eval", "eval:baseline")), ("creditcoach.answer", ("app",))]
    assert obs.run_tags() == ["app"]
    monkeypatch.setattr(obs, "_run", [])
    assert obs.run_tags() == ["script", "script:evals"]
