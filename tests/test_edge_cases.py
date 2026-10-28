"""Task 32: edge cases end in a graceful fallback, never a crash.

    Tool timeout or outage   the account tool times out, the tool server can't start, hangs at startup or dies
                             mid-call: every call becomes DATA_UNAVAILABLE, the answer goes on, and a figure confirmed
                             earlier in the session comes back as ``last_confirmed`` (requirements.md §4 #45, §6)
    Ambiguous "this loan"    a CLARIFY note asks the model to find out which loan first (#47)
    No library content       retrieval fails or finds nothing: the answer goes on, told the library has nothing (#48);
                             the user's profile can't be read: the answer goes on without it

No API key needed: the model is scripted, and the tool server is the real one over stdio (or a broken one).

Run:
    uv run pytest tests/test_edge_cases.py -v
"""

import asyncio
import json
import re
import sys
from types import SimpleNamespace

import pytest
from mcp import StdioServerParameters

from creditcoach import config
from creditcoach.agent import clarify, mcp_host, pipeline
from creditcoach.agent.mcp_host import McpHost
from creditcoach.evals.live import TimingOutAccounts
from creditcoach.guardrails import checks
from creditcoach.memory import store

BROKEN = StdioServerParameters(command=sys.executable, args=["-c", "import sys; sys.exit(1)"])  # exits at once
SILENT = StdioServerParameters(command=sys.executable, args=["-c", "import time; time.sleep(30)"])  # never answers


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEMORY_DIR", tmp_path / "memory")
    monkeypatch.setattr(mcp_host, "_confirmed", type(mcp_host._confirmed)())
    monkeypatch.setattr(checks, "model_review", lambda question, answer, projection, product: [])


def call(host_class=McpHost, name="get_account_summary", **kwargs):
    async def body():
        async with host_class("USR-001", **kwargs) as host:
            return host, await host.call(name, {})
    return asyncio.run(body())


# ---- the tool server is down ----

def test_a_server_that_cant_start_gives_data_unavailable_not_an_exception(spans):
    host, result = call(server=BROKEN)
    assert host.unavailable and host.openai_tools == []
    assert result["error"]["code"] == "DATA_UNAVAILABLE" and result["error"]["retryable"]
    assert host.calls[0].code == "DATA_UNAVAILABLE"
    tool_span = next(s for s in spans.get_finished_spans() if s.name == "tool.get_account_summary")
    assert tool_span.status.status_code.name == "ERROR"  # still counted as a tool failure (Task 31 dashboard)


def test_a_server_that_never_answers_times_out_at_startup(monkeypatch):
    monkeypatch.setattr(mcp_host, "STARTUP_SECONDS", 0.5)
    host, result = call(server=SILENT)
    assert "didn't start within 0.5 seconds" in host.unavailable
    assert result["error"]["code"] == "DATA_UNAVAILABLE"


def test_a_server_that_dies_mid_call_gives_data_unavailable():
    class Dying(McpHost):
        async def __aenter__(self):
            await super().__aenter__()
            self._session.call_tool = self._die
            return self

        async def _die(self, name, args):
            raise ConnectionResetError("server went away")

    host, result = call(Dying)
    assert result["error"]["code"] == "DATA_UNAVAILABLE" and "ConnectionResetError" in result["error"]["message"]
    assert host.calls[0].attempts == 2  # retried once, as any retryable error


def test_the_answer_goes_on_when_the_tool_server_is_down(monkeypatch):
    seen = []

    class Down(McpHost):
        def __init__(self, user_id, **kwargs):
            super().__init__(user_id, **{**kwargs, "server": BROKEN})

    def model(messages, tools, model=None):
        seen.append((messages, tools))
        return SimpleNamespace(content="I can't pull your latest data right now. Try again shortly.", tool_calls=None), "m"

    monkeypatch.setattr(pipeline, "McpHost", Down)
    monkeypatch.setattr(pipeline, "chat_with_tools", model)
    a = pipeline.answer("What's my utilization right now?", user_id="USR-001")
    assert a.text.startswith("I can't pull") and [c.code for c in a.tool_calls] == ["DATA_UNAVAILABLE"] * 2
    messages, tools = seen[0]
    assert tools is None  # no data tools to offer, and no empty list sent to the API
    assert all(json.loads(m["content"])["error"]["code"] == "DATA_UNAVAILABLE" for m in messages if m["role"] == "tool")


# ---- last confirmed ----

def test_a_failed_lookup_carries_the_figure_confirmed_earlier_in_the_session():
    _, first = call(scope="S1")
    assert first["ok"]
    _, again = call(TimingOutAccounts, scope="S1")
    assert again["error"]["code"] == "DATA_UNAVAILABLE"
    assert again["last_confirmed"]["result"]["totals"] == first["totals"]
    assert re.fullmatch(r"\d{2}:\d{2} IST on \d{2} \w{3} \d{4}", again["last_confirmed"]["at"])


def test_last_confirmed_stays_within_its_session_and_only_for_data_unavailable():
    call(scope="S1")
    assert "last_confirmed" not in call(TimingOutAccounts, scope="S2")[1]       # another session
    assert "last_confirmed" not in call(TimingOutAccounts)[1]                    # no session: nothing kept
    out_of_range = {"ok": False, "error": {"code": "PERIOD_OUT_OF_RANGE"}}
    assert mcp_host.confirm("S1", "USR-001", "get_account_summary", {}, out_of_range) is out_of_range


def test_last_confirmed_results_are_capped(monkeypatch):
    monkeypatch.setattr(mcp_host, "CONFIRMED_KEEP", 3)
    for i in range(5):
        mcp_host.confirm(f"S{i}", "USR-001", "get_account_summary", {}, {"ok": True, "n": i})
    assert [k[0] for k in mcp_host._confirmed] == ["S2", "S3", "S4"]


def test_the_pipeline_keeps_last_confirmed_per_memory_session(monkeypatch):
    seen = []

    def model(messages, tools, model=None):
        seen.append(messages)
        return SimpleNamespace(content="Your utilization, as last confirmed, was 37.4%.", tool_calls=None), "m"

    monkeypatch.setattr(pipeline, "chat_with_tools", model)
    monkeypatch.setattr(pipeline, "retrieve", lambda q, k=3, where=None: [])
    session = store.start_session("USR-001", source="cli")
    pipeline.answer("What's my utilization right now?", user_id="USR-001", session=session)
    monkeypatch.setattr(pipeline, "McpHost", TimingOutAccounts)
    pipeline.answer("And now?", user_id="USR-001", session=session)
    account = json.loads([m for m in seen[-1] if m["role"] == "tool"][-1]["content"])
    assert account["error"]["code"] == "DATA_UNAVAILABLE"
    assert account["last_confirmed"]["result"]["totals"]["overall_utilization_ratio"] == 0.374


# ---- ambiguous references ----

@pytest.mark.parametrize("question", ["Should I take this loan?", "Should I accept that offer?",
                                      "Is this app safe to borrow from?", "Should I take the loan my bank offered?"])
def test_an_unexplained_loan_gets_a_clarify_note(question):
    assert clarify.note(question, []).startswith("CLARIFY")


@pytest.mark.parametrize("question, earlier", [
    ("Should I take this ₹50,000 loan?", []),                                  # terms given
    ("Should I take out this payday loan?", []),                               # a predatory product (G2 handles it)
    ("Should I take this loan?", ["My bank offered me a personal loan at 14% for 3 years."]),
    ("Should I close the loan early?", []),                                    # their own loan: the tools show it
    ("What does this mean for my score?", []),
])
def test_no_note_once_the_loan_is_named_or_for_other_questions(question, earlier):
    assert clarify.note(question, earlier) == ""


def test_the_clarify_note_reaches_the_model_only_until_the_loan_is_described(monkeypatch):
    seen = []
    monkeypatch.setattr(pipeline, "chat_with_tools", lambda messages, tools, model=None: (
        seen.append(messages) or SimpleNamespace(content="Which loan is it, and what are its terms?", tool_calls=None),
        "m"))
    monkeypatch.setattr(pipeline, "retrieve", lambda q, k=3, where=None: [])
    pipeline.answer("Should I take this loan?", user_id="USR-001")
    assert any(m["content"].startswith("CLARIFY") for m in seen[-1] if m["role"] == "system")
    history = [{"role": "user", "content": "Should I take this loan?"},
               {"role": "assistant", "content": "Which loan is it, and what are its terms?"}]
    pipeline.answer("It's from an instant loan app, ₹20,000 for 30 days.", user_id="USR-001", history=history)
    assert not any(m["content"].startswith("CLARIFY") for m in seen[-1] if m["role"] == "system")


# ---- no library content, no profile ----

def test_the_answer_goes_on_when_retrieval_fails(monkeypatch, spans):
    seen = []

    def broken(q, k=3, where=None):
        raise RuntimeError("Vector store not built. Run: uv run python -m creditcoach.rag.ingest")

    monkeypatch.setattr(pipeline, "retrieve", broken)
    monkeypatch.setattr(pipeline, "chat_with_tools", lambda messages, tools, model=None: (
        seen.append(messages) or SimpleNamespace(content="I don't have specific information on that.", tool_calls=None),
        "m"))
    a = pipeline.answer("Is buy now, pay later bad for my score?", user_id="USR-001")
    assert a.passages == [] and a.text.startswith("I don't have")
    assert pipeline.NO_PASSAGES in seen[0][1]["content"]
    retrieval = next(s for s in spans.get_finished_spans() if s.name == "retrieval")
    assert [e.name for e in retrieval.events] == ["retrieval.failed", "retrieval.empty"]


def test_no_passages_tells_the_model_not_to_answer_from_its_own_knowledge():
    context = pipeline.build_context([], "USR-001")
    assert "don't explain it from your own knowledge" in context


def test_the_answer_goes_on_when_the_profile_cant_be_read(monkeypatch):
    def down(user_id):
        raise ConnectionError("Neon unreachable")

    monkeypatch.setattr(pipeline, "load_user_data", down)
    context = pipeline.build_context([], "USR-001")
    assert pipeline.NO_PROFILE in context and "USER PROFILE" in context
