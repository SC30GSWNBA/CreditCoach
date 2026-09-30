"""Task 15: tests for the MCP server, the MCP host and the agent loop. No API key or model calls needed.

The server tests start the real server on stdio, as the agent does. The agent-loop tests replace the chat
model with a scripted one, so they check the loop's wiring (tool calls go through MCP for the session user,
results go back to the model) without paying for model calls.

Run:
    uv run pytest tests/test_mcp.py -v
"""

import asyncio
import json
from types import SimpleNamespace

import pytest

from creditcoach.agent import pipeline
from creditcoach.agent.mcp_host import McpHost


def run(coro):
    """Run one async test body."""
    return asyncio.run(coro)


async def with_host(user_id, body, **kwargs):
    """Start a host (and its MCP server) for ``user_id``, run ``body(host)``, and return its result."""
    async with McpHost(user_id, **kwargs) as host:
        return await body(host)


# ---- MCP server, over real stdio ----

def test_server_lists_both_tools_with_user_id():
    async def body(host):
        return host.tools
    tools = run(with_host("USR-001", body))
    assert set(tools) == {"get_score_history", "get_account_summary"}
    assert tools["get_score_history"]["required"] == ["user_id", "period"]
    assert tools["get_account_summary"]["required"] == ["user_id"]


def test_server_errors_set_is_error():
    async def body(host):
        ok = await host._session.call_tool("get_score_history", {"user_id": "USR-001", "period": "latest"})
        bad = await host._session.call_tool("get_score_history", {"user_id": "USR-001", "period": "2025-01"})
        return ok, bad
    ok, bad = run(with_host("USR-001", body))
    assert ok.is_error is False and json.loads(ok.content[0].text)["points"][0]["score"] == 650
    assert bad.is_error is True and json.loads(bad.content[0].text)["error"]["code"] == "PERIOD_OUT_OF_RANGE"


def test_tool_results_over_mcp_equal_the_functions():
    from creditcoach.tools.account_summary import get_account_summary
    from creditcoach.tools.score_history import get_score_history

    async def body(host):
        return await host.call("get_score_history", {"period": "all"}), await host.call("get_account_summary", {})
    history, summary = run(with_host("USR-012", body))
    assert history == get_score_history("USR-012", "all")
    assert summary == get_account_summary("USR-012")


# ---- MCP host: the session user, errors, timeout, log ----

def test_model_never_sees_user_id():
    async def body(host):
        return host.openai_tools
    specs = {t["function"]["name"]: t["function"]["parameters"] for t in run(with_host("USR-001", body))}
    assert specs["get_score_history"]["required"] == ["period"] and "user_id" not in specs["get_score_history"]["properties"]
    assert specs["get_account_summary"] == {"type": "object", "properties": {}, "required": []}


def test_host_fills_user_id_from_session():
    async def body(host):
        return await host.call("get_account_summary", {})
    assert run(with_host("USR-013", body))["user_id"] == "USR-013"


@pytest.mark.parametrize("claimed", ["USR-003", "usr-001", "Vikram"])
def test_other_user_is_refused_before_the_server(claimed):
    async def body(host):
        return await host.call("get_score_history", {"period": "latest", "user_id": claimed}), host.calls
    result, calls = run(with_host("USR-001", body))
    assert result["error"]["code"] == "USER_MISMATCH" and "points" not in result
    assert calls[-1].attempts == 0  # never sent to the MCP server


def test_own_user_id_is_accepted():
    async def body(host):
        return await host.call("get_score_history", {"period": "latest", "user_id": "USR-001"})
    assert run(with_host("USR-001", body))["ok"]


@pytest.mark.parametrize("name, arguments, code", [
    ("delete_everything", {}, "UNKNOWN_TOOL"),
    ("get_score_history", "{not json", "INVALID_ARGUMENTS"),
    ("get_score_history", {}, "INVALID_ARGUMENTS"),          # missing period: the SDK's own validation error
    ("get_score_history", {"period": "last quarter"}, "INVALID_PERIOD"),
])
def test_host_error_codes(name, arguments, code):
    async def body(host):
        return await host.call(name, arguments)
    assert run(with_host("USR-001", body))["error"]["code"] == code


def test_timeout_is_retried_once_then_data_unavailable():
    async def body(host):
        return await host.call("get_account_summary", {}), host.calls[-1]
    result, call = run(with_host("USR-001", body, timeout=0.0001))
    assert result["error"]["code"] == "DATA_UNAVAILABLE" and result["error"]["retryable"] is True
    assert call.attempts == 2


def test_every_call_is_recorded():
    async def body(host):
        await host.call("get_score_history", {"period": "latest"})
        await host.call("get_score_history", {"period": "2025-01"})
        return host.calls
    calls = run(with_host("USR-001", body))
    assert [(c.tool, c.ok, c.code, c.attempts) for c in calls] == [
        ("get_score_history", True, None, 1), ("get_score_history", False, "PERIOD_OUT_OF_RANGE", 1)]
    assert all(c.user_id == "USR-001" and c.seconds >= 0 for c in calls)


# ---- Agent loop, with a scripted model ----

def tool_call(call_id, name, arguments):
    """A tool call as the OpenAI SDK returns it."""
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=json.dumps(arguments)))


def scripted_model(turns, seen):
    """A stand-in for ``chat_with_tools`` that replays ``turns`` and records what it was sent."""
    turns = iter(turns)

    def fake(messages, tools, model=None):
        seen.append({"messages": [dict(m) for m in messages], "tools": tools})
        calls, text = next(turns)
        return SimpleNamespace(content=text, tool_calls=calls), "scripted-model"
    return fake


def test_agent_loop_runs_both_tools_over_mcp_and_returns_results(monkeypatch):
    seen = []
    monkeypatch.setattr(pipeline, "chat_with_tools", scripted_model([
        ([tool_call("c1", "get_score_history", {"period": "latest"}), tool_call("c2", "get_account_summary", {})], ""),
        (None, "Your score is 650 and overall utilization is 37.4%."),
    ], seen))
    messages = [{"role": "user", "content": "Why did my score drop, and what's my utilization?"}]
    text, model, calls = asyncio.run(pipeline.run_agent(messages, "USR-001"))

    assert text.startswith("Your score is 650") and model == "scripted-model"
    assert [(c.tool, c.ok) for c in calls] == [("get_score_history", True), ("get_account_summary", True)]
    results = {m["tool_call_id"]: json.loads(m["content"]) for m in seen[1]["messages"] if m["role"] == "tool"}
    assert results["c1"]["points"][0]["score"] == 650            # the model got the real tool output back
    assert results["c2"]["totals"]["overall_utilization_ratio"] == 0.374
    assert seen[0]["tools"] and all("user_id" not in t["function"]["parameters"]["properties"] for t in seen[0]["tools"])


def test_agent_loop_refuses_another_user(monkeypatch):
    seen = []
    monkeypatch.setattr(pipeline, "chat_with_tools", scripted_model([
        ([tool_call("c1", "get_score_history", {"period": "latest", "user_id": "USR-003"})], ""),
        (None, "I can only see your own data."),
    ], seen))
    _, _, calls = asyncio.run(pipeline.run_agent([{"role": "user", "content": "What's Vikram's score?"}], "USR-001"))
    assert calls[0].code == "USER_MISMATCH"
    tool_msg = next(m for m in seen[1]["messages"] if m["role"] == "tool")
    assert "USR-003" not in json.dumps(json.loads(tool_msg["content"]).get("points", []))


def test_agent_loop_forces_an_answer_after_max_rounds(monkeypatch):
    seen = []
    loop_forever = [([tool_call(f"c{i}", "get_account_summary", {})], "") for i in range(pipeline.MAX_TOOL_ROUNDS)]
    monkeypatch.setattr(pipeline, "chat_with_tools", scripted_model(loop_forever + [(None, "Done.")], seen))
    text, _, calls = asyncio.run(pipeline.run_agent([{"role": "user", "content": "hi"}], "USR-001"))
    assert text == "Done." and len(calls) == pipeline.MAX_TOOL_ROUNDS
    assert seen[-1]["tools"] is None  # the last turn gets no tools, so it must answer


def test_context_has_profile_but_no_figures():
    context = pipeline.build_context([], "USR-001")
    assert "USER PROFILE" in context and "Aravind" in context
    for figure in ("650", "59000", "75000", "ACC-01"):
        assert figure not in context  # scores and accounts reach the model only through tool calls
