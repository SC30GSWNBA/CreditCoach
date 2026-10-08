"""Task 15: the MCP host, which connects the agent to the CreditCoach MCP server for one signed-in user.

The host starts ``creditcoach.tools.server`` on stdio, lists its tools, and runs every tool call the model asks
for. It does the jobs ``docs/tools.md`` gives to "the host":

    Session user   The model is shown each tool without its ``user_id`` parameter. The host fills ``user_id``
                   from the signed-in session. If the model passes any other id anyway, the call is refused
                   with ``USER_MISMATCH`` and never reaches the server (§1 rule 2, requirements.md §4 #49).
    Timeout        A call that takes longer than ``TIMEOUT_SECONDS`` becomes ``DATA_UNAVAILABLE`` (retryable).
    Retry          A retryable error is retried once (§4).
    Log            Every call is recorded as a ``ToolCall`` (tool, arguments, ok, error code, latency, attempts)
                   and logged as one JSON line, for the Week 4 tool-failure rate.

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
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, get_default_environment, stdio_client

from creditcoach import config
from creditcoach.tools.common import error

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5.0


def server_params() -> StdioServerParameters:
    """How to start the tool server, reading the dataset from the same backend as this process.

    Built when a session opens, not at import, so a backend set at run time (tests force "files") reaches the
    server too; on its own the server would pick Neon whenever ``.env`` has ``DATABASE_URL``.
    """
    return StdioServerParameters(command=sys.executable, args=["-m", "creditcoach.tools.server"], cwd=str(config.ROOT),
                                 env={**get_default_environment(), "CREDITCOACH_DATA_BACKEND": config.DATA_BACKEND})


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
    """
    tool: str
    arguments: dict
    user_id: str
    result: dict
    seconds: float
    attempts: int

    @property
    def ok(self) -> bool:
        """True if the tool returned data."""
        return bool(self.result.get("ok"))

    @property
    def code(self) -> str | None:
        """The error code, or None on success."""
        return None if self.ok else self.result.get("error", {}).get("code")


class McpHost:
    """An MCP client session for one signed-in user. Use as ``async with McpHost(user_id) as host``."""

    def __init__(self, user_id: str, timeout: float = TIMEOUT_SECONDS, server: StdioServerParameters | None = None):
        self.user_id = user_id
        self.timeout = timeout
        self.server = server
        self.calls: list[ToolCall] = []
        self.tools: dict[str, dict] = {}  # tool name -> input schema, as the server lists it

    async def __aenter__(self) -> "McpHost":
        self._stack = AsyncExitStack()
        try:
            read, write = await self._stack.enter_async_context(stdio_client(self.server or server_params()))
            self._session = await self._stack.enter_async_context(ClientSession(read, write))
            await self._session.initialize()
            listed = (await self._session.list_tools()).tools
        except BaseException:
            await self._stack.aclose()  # stop the server process if startup fails part-way
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
        start = time.perf_counter()
        args, result, attempts = self._check(name, arguments)
        if result is None:
            for attempts in (1, 2):
                result = await self._send(name, {**args, "user_id": self.user_id})
                if result.get("ok") or not result["error"].get("retryable"):
                    break
        call = ToolCall(tool=name, arguments=args,
                        user_id=self.user_id, result=result, seconds=time.perf_counter() - start, attempts=attempts)
        self.calls.append(call)
        log.info("tool_call %s", json.dumps({"tool": name, "user_id": self.user_id, "arguments": call.arguments,
                                              "ok": call.ok, "code": call.code, "attempts": attempts,
                                              "ms": round(call.seconds * 1000)}, ensure_ascii=False))
        return result

    def _check(self, name: str, arguments) -> tuple[dict, dict | None, int]:
        """Validate a call before it is sent. Returns (arguments, refusal or None, attempts)."""
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments or "{}")
            except json.JSONDecodeError:
                return {"raw": arguments}, error("INVALID_ARGUMENTS", f"Arguments for {name} aren't valid JSON."), 0
        args = dict(arguments or {})
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
        text = res.content[0].text if res.content else ""
        try:
            result = res.structured_content or json.loads(text)
        except json.JSONDecodeError:
            result = None
        if not isinstance(result, dict) or "ok" not in result:  # e.g. the SDK's own argument-validation error
            return error("INVALID_ARGUMENTS", text or f"{name} returned no content.")
        return result
