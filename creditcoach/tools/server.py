"""Task 15: the CreditCoach MCP server, exposing ``get_score_history`` and ``get_account_summary``.

Built on the ``mcp`` Python SDK (v2, where FastMCP is called ``MCPServer``). Each tool is a thin wrapper around
the Task 13 and Task 14 functions, so the tool logic and its tests live in one place. Results follow
``docs/tools.md`` §4: a success is the JSON object from the spec; an error is the error envelope with the MCP
result's ``isError`` set, so a host can count failures without parsing text. Both tools are read-only.

The server trusts the ``user_id`` it is given. Choosing that id is the host's job: ``creditcoach.agent.mcp_host``
fills it from the signed-in session and refuses any call for another user before it reaches this server.

Run it on stdio (the transport the agent uses; also works with any MCP client, such as the MCP Inspector):
    uv run python -m creditcoach.tools.server
"""

import json
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field

from creditcoach.tools.account_summary import get_account_summary as account_summary
from creditcoach.tools.score_history import get_score_history as score_history

server = MCPServer(
    name="creditcoach",
    log_level="WARNING",  # stdout carries the protocol; keep stderr for real problems
    instructions="Read-only access to one CreditCoach user's simulated credit data (Indian context: ₹ amounts, "
                 "300-900 scores). Every figure about the user must come from these tools.",
)
READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)
UserId = Annotated[str, Field(description='Dataset user id, e.g. "USR-001". Set by the host from the signed-in '
                                          "session.")]


def as_mcp(result: dict) -> CallToolResult:
    """Wrap a tool's result dict as an MCP result: JSON text plus structured content, ``isError`` on failure."""
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False))],
                          structured_content=result, is_error=not result.get("ok", False))


@server.tool(structured_output=False, annotations=READ_ONLY, description=(
    "Monthly credit scores for the user, with each month's score change and the main factor behind it, plus a "
    "summary (start score, end score, net change, lowest and highest month). Use it for any question about the "
    "user's score, a score change, or why it moved. Periods are anchored to the dataset's latest month (as_of), "
    "not today's date."))
def get_score_history(
    user_id: UserId,
    period: Annotated[str, Field(description=(
        'Which months to return: "latest" (this month), "last_N_months" with N from 1 to 24 (e.g. '
        '"last_3_months"), one month as "YYYY-MM", a range as "YYYY-MM:YYYY-MM", or "all".'))],
) -> CallToolResult:
    return as_mcp(score_history(user_id, period))


@server.tool(structured_output=False, annotations=READ_ONLY, description=(
    "Every account the user holds (credit cards and loans) with balances and limits in ₹, each card's "
    "utilization ratio, totals (overall utilization across all cards, loan balances, total debt), and a "
    "high_risk_product flag on instant-loan-app accounts. Use it for questions about balances, limits, "
    "utilization, debt or the user's accounts. Ratios are decimals: 0.374 means 37.4%."))
def get_account_summary(user_id: UserId) -> CallToolResult:
    return as_mcp(account_summary(user_id))


if __name__ == "__main__":
    server.run("stdio")
