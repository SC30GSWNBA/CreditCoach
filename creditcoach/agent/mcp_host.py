"""Task 15: the MCP host, which connects the agent to the CreditCoach MCP server for one signed-in user.

The host starts ``creditcoach.tools.server`` on stdio, lists its tools, and runs every tool call the model asks
for. It does the jobs ``docs/tools.md`` gives to "the host":

    Session user   The model is shown each tool without its ``user_id`` parameter. The host fills ``user_id``
                   from the signed-in session. If the model passes any other id anyway, the call is refused
                   with ``USER_MISMATCH`` and never reaches the server (§1 rule 2, requirements.md §4 #49).
    Timeout        A call that takes longer than ``TIMEOUT_SECONDS`` becomes ``DATA_UNAVAILABLE`` (retryable).
    Retry          A retryable error is retried once (§4).
    Server down    (Task 32) If the server can't start, doesn't answer within ``STARTUP_SECONDS``, or fails during
                   a call, every call becomes ``DATA_UNAVAILABLE`` instead of raising, so the answer goes on from
                   the library and says the user's data can't be read right now.
    Last confirmed (Task 32) With a ``scope`` (the memory session), each successful result is kept in this process.
                   If the same call later fails with ``DATA_UNAVAILABLE``, the error carries that result as
                   ``last_confirmed`` with when it was read, so the answer may share it, labeled as last confirmed
                   and never as current (requirements.md §4 #45 and §6).
    Log            Every call is recorded as a ``ToolCall`` (tool, arguments, ok, error code, latency, attempts)
                   and logged as one JSON line, for the Week 4 tool-failure rate.
    Trace          Every call is a ``tool.<name>`` span in the request's trace (Task 26, ``creditcoach.observability``);
                   a failed call has ERROR status and a ``tool.failure`` event with the error code.
    Cache          A successful result is kept for a few minutes under the signed-in user's own key (Task 22,
                   ``creditcoach.cache``), so repeated lookups skip the server. Errors are never cached, and the
                   user check above always runs first.

Host-side error codes, added to the spec's codes: ``UNKNOWN_TOOL`` (the model named a tool that doesn't exist)
and ``INVALID_ARGUMENTS`` (the model's arguments weren't valid JSON or failed the server's validation).

Example:
    >>> async with McpHost("USR-001") as host:
    ...     host.openai_tools                      # tool schemas for the chat model, without user_id
    ...     await host.call("get_account_summary", {})
"""

import asyncio
import json
import logging
import sys
import threading
import time
from collections import OrderedDict
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, get_default_environment, stdio_client

from creditcoach import cache, config
from creditcoach import observability as obs
from creditcoach.tools.common import error

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5.0
STARTUP_SECONDS = 20.0  # starting the server and listing its tools; normally about 2 s
CONFIRMED_KEEP = 500    # last confirmed results kept in this process, oldest dropped first
IST = timezone(timedelta(hours=5, minutes=30), "IST")

_confirmed: OrderedDict[tuple, dict] = OrderedDict()  # (scope, user, tool, arguments) -> {"at": ..., "result": ...}
_confirmed_lock = threading.Lock()


def server_params() -> StdioServerParameters:
    """How to start the tool server, reading the dataset from the same backend as this process.

    Built when a session opens, not at import, so a backend set at run time (tests force "files") reaches the
    server too; on its own the server would pick Neon whenever ``.env`` has ``DATABASE_URL``.

    The MCP client starts the server with only a minimal environment, so ``DATABASE_URL`` is passed on too. Locally
    the server would also find it in ``.env``, but a hosted deployment (Railway) has no ``.env``: its secrets are
    environment variables only, and without this every tool call failed with ``DATA_UNAVAILABLE``.
    """
    env = {**get_default_environment(), "CREDITCOACH_DATA_BACKEND": config.DATA_BACKEND}
    if config.DATABASE_URL:
        env["DATABASE_URL"] = config.DATABASE_URL
    return StdioServerParameters(command=sys.executable, args=["-m", "creditcoach.tools.server"], cwd=str(config.ROOT),
                                 env=env)


@dataclass
class ToolCall:
    """One tool call the model asked for, as the host handled it.

    Attributes:
        tool: The tool name the model asked for.
        arguments: The arguments the model sent (``user_id`` included only if the model tried to set one).
        user_id: The signed-in user the call ran for.
        result: The tool's result: the spec's success object or the error envelope.
        seconds: Time from the host receiving the call to having the result, across all attempts.
        attempts: 1, or 2 when a retryable error was retried; 0 if the call never reached the server.
        cached: True if the result came from the cache instead of the server.
    """
    tool: str
    arguments: dict
    user_id: str
    result: dict
    seconds: float
    attempts: int
    cached: bool = False

    @property
    def ok(self) -> bool:
        """True if the tool returned data."""
        return bool(self.result.get("ok"))

    @property
    def code(self) -> str | None:
        """The error code, or None on success."""
        return None if self.ok else self.result.get("error", {}).get("code")


def tool_key(user_id: str, name: str, args: dict) -> str:
    """The cache key for one tool call: the signed-in user, the tool, its arguments, and where the data is read from."""
    return cache.key("tool", name, args, config.DATA_BACKEND, scope=user_id)


def cached_call(user_id: str, name: str, args: dict) -> ToolCall | None:
    """A recent successful result for this call, as a ``ToolCall``, without starting the MCP server; else None."""
    start = time.perf_counter()
    with obs.span(f"tool.{name}", **tool_attributes(name, args, user_id)):
        result = cache.get("tool", tool_key(user_id, name, args), tool=name, user_id=user_id)
        if result is None:
            obs.annotate(**{"tool.cached": False, "tool.outcome": "not cached"})
            return None
        call = ToolCall(tool=name, arguments=args, user_id=user_id, result=result,
                        seconds=time.perf_counter() - start, attempts=0, cached=True)
        trace_call(call)
        return call


def tool_attributes(name: str, args, user_id: str) -> dict:
    """The attributes every ``tool.<name>`` span starts with."""
    return {"langfuse.observation.type": "tool", "tool.name": name, "tool.arguments": args, "user.id": user_id,
            "langfuse.observation.input": args}


def trace_call(call: ToolCall) -> None:
    """Record a finished call on the current ``tool.<name>`` span; a failed call marks the span as failed."""
    obs.annotate(**{"tool.ok": call.ok, "tool.code": call.code, "tool.attempts": call.attempts,
                    "tool.cached": call.cached, "tool.ms": round(call.seconds * 1000, 1),
                    "langfuse.observation.output": call.result})
    if not call.ok:
        err = call.result.get("error", {})
        obs.event("tool.failure", tool=call.tool, code=call.code, message=err.get("message"),
                  retryable=err.get("retryable"), attempts=call.attempts)
        obs.fail(f"{call.tool} failed: {call.code}")


def confirm(scope: str | None, user_id: str, name: str, args: dict, result: dict) -> dict:
    """Keep a successful result as the last confirmed one for this call, or attach the last confirmed result to a
    ``DATA_UNAVAILABLE`` error. Returns the result to give the model (unchanged unless something was attached)."""
    if not scope:
        return result
    key = (scope, user_id, name, json.dumps(args, sort_keys=True))
    with _confirmed_lock:
        if result.get("ok"):
            _confirmed[key] = {"at": datetime.now(IST).strftime("%H:%M IST on %d %b %Y"), "result": result}
            _confirmed.move_to_end(key)
            while len(_confirmed) > CONFIRMED_KEEP:
                _confirmed.popitem(last=False)
            return result
        earlier = _confirmed.get(key)
    if earlier and result.get("error", {}).get("code") == "DATA_UNAVAILABLE":
        return {**result, "last_confirmed": earlier}
    return result


class McpHost:
    """An MCP client session for one signed-in user. Use as ``async with McpHost(user_id) as host``."""

    def __init__(self, user_id: str, timeout: float = TIMEOUT_SECONDS, server: StdioServerParameters | None = None,
                 scope: str | None = None):
        self.user_id = user_id
        self.timeout = timeout
        self.server = server
        self.scope = scope  # the memory session, for last confirmed results; None keeps none
        self.unavailable: str | None = None  # why the server can't be used, once startup has failed
        self.calls: list[ToolCall] = []
        self.tools: dict[str, dict] = {}  # tool name -> input schema, as the server lists it

    async def __aenter__(self) -> "McpHost":
        self._stack = AsyncExitStack()
        try:
            read, write = await self._stack.enter_async_context(stdio_client(self.server or server_params()))
            self._session = await self._stack.enter_async_context(ClientSession(read, write))
            await asyncio.wait_for(self._session.initialize(), STARTUP_SECONDS)
            listed = (await asyncio.wait_for(self._session.list_tools(), STARTUP_SECONDS)).tools
        except Exception as exc:  # degrade: every call reports DATA_UNAVAILABLE (Task 32)
            await self._stack.aclose()  # stop the server process if startup fails part-way
            self.unavailable = (f"the tool server didn't start within {STARTUP_SECONDS:g} seconds"
                                if isinstance(exc, TimeoutError) else f"the tool server couldn't start ({type(exc).__name__})")
            log.error("MCP server unavailable for %s: %s", self.user_id, self.unavailable, exc_info=exc)
            obs.event("tool.server_unavailable", reason=self.unavailable)
            self.tools, self._descriptions = {}, {}
            return self
        except BaseException:
            await self._stack.aclose()
            raise
        self.tools = {t.name: t.input_schema for t in listed}
        self._descriptions = {t.name: t.description or "" for t in listed}
        return self

    async def __aexit__(self, *exc) -> None:
        await self._stack.__aexit__(*exc)

    @property
    def openai_tools(self) -> list[dict]:
        """The tools as OpenAI function definitions for the chat model, with ``user_id`` removed."""
        specs = []
        for name, schema in self.tools.items():
            properties = {k: v for k, v in schema.get("properties", {}).items() if k != "user_id"}
            required = [k for k in schema.get("required", []) if k != "user_id"]
            specs.append({"type": "function", "function": {
                "name": name, "description": self._descriptions[name],
                "parameters": {"type": "object", "properties": properties, "required": required}}})
        return specs

    async def call(self, name: str, arguments: dict | str | None) -> dict:
        """Run one tool call for the signed-in user and return its result (never raises for tool errors).

        Args:
            name: The tool the model asked for.
            arguments: The model's arguments, as a dict or the raw JSON string from the model.

        Returns:
            The tool's success object or an error envelope (``docs/tools.md`` §4).
        """
        with obs.span(f"tool.{name}", **tool_attributes(name, arguments, self.user_id)):
            start = time.perf_counter()
            args, result, attempts = self._check(name, arguments)
            cached = False
            if result is None:
                key = tool_key(self.user_id, name, args)
                result = cache.get("tool", key, tool=name, user_id=self.user_id)
                cached = result is not None
            if result is None:
                for attempts in (1, 2):
                    result = await self._send(name, {**args, "user_id": self.user_id})
                    if result.get("ok") or not result["error"].get("retryable"):
                        break
                    if attempts == 1:
                        obs.event("tool.retry", code=result["error"].get("code"))
                if result.get("ok"):
                    cache.put("tool", key, result, tool=name, user_id=self.user_id)
            if attempts or cached:  # it reached the server or the cache: not refused by the checks below
                result = confirm(self.scope, self.user_id, name, args, result)
            call = ToolCall(tool=name, arguments=args, user_id=self.user_id, result=result,
                            seconds=time.perf_counter() - start, attempts=attempts, cached=cached)
            self.calls.append(call)
            trace_call(call)
            log.info("tool_call %s", json.dumps({"tool": name, "user_id": self.user_id, "arguments": call.arguments,
                                                  "ok": call.ok, "code": call.code, "attempts": attempts,
                                                  "cached": cached, "ms": round(call.seconds * 1000),
                                                  "trace_id": obs.trace_id()}, ensure_ascii=False))
            return result

    def _check(self, name: str, arguments) -> tuple[dict, dict | None, int]:
        """Validate a call before it is sent. Returns (arguments, refusal or None, attempts)."""
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments or "{}")
            except json.JSONDecodeError:
                return {"raw": arguments}, error("INVALID_ARGUMENTS", f"Arguments for {name} aren't valid JSON."), 0
        args = dict(arguments or {})
        if self.unavailable:
            return args, error("DATA_UNAVAILABLE", f"Can't read the data right now: {self.unavailable}.",
                               retryable=True), 1
        if name not in self.tools:
            return args, error("UNKNOWN_TOOL", f"No tool named {name}.", tools=sorted(self.tools)), 0
        claimed = args.pop("user_id", None)
        if claimed not in (None, "", self.user_id):
            return {**args, "user_id": claimed}, error(
                "USER_MISMATCH", "Tools only return the signed-in user's own data.", requested_user_id=claimed), 0
        return args, None, 0

    async def _send(self, name: str, args: dict) -> dict:
        """Call the MCP server once, with the timeout, and turn the MCP result into a result dict."""
        try:
            res = await asyncio.wait_for(self._session.call_tool(name, args), self.timeout)
        except TimeoutError:
            return error("DATA_UNAVAILABLE", f"{name} took longer than {self.timeout:g} seconds.", retryable=True)
        except Exception as exc:  # the server process died or the connection broke (Task 32)
            log.error("MCP call %s failed for %s", name, self.user_id, exc_info=exc)
            return error("DATA_UNAVAILABLE", f"{name} couldn't reach the tool server ({type(exc).__name__}).",
                         retryable=True)
        text = res.content[0].text if res.content else ""
        try:
            result = res.structured_content or json.loads(text)
        except json.JSONDecodeError:
            result = None
        if not isinstance(result, dict) or "ok" not in result:  # e.g. the SDK's own argument-validation error
            return error("INVALID_ARGUMENTS", text or f"{name} returned no content.")
        return result
