"""Task 15: run one live question through the MCP agent loop and write its trace as evidence.

Definition of Done: the agent calls both tools via MCP and uses their results in a live response. This script
asks USR-001 (Aravind) a question that needs both tools (requirements.md §3 #1 and #2 together), then records:
the tools the MCP server listed, every tool call (the model's arguments, the user id the host filled in, the
latency and the full result), the MCP host's log lines, the final answer, and a table tracing each key figure
in the answer back to the tool output. It passes only if both tools were called through MCP and succeeded, and
the answer states the figures from their output.

Writes:
    docs/evidence/week-2/task-15-mcp-round-trip.md

Run (needs OPENROUTER_API_KEY and the vector store; about 2-3 paid model calls):
    uv run python scripts/task15_mcp_round_trip.py
"""

import asyncio
import json
import logging
import re
import sys
from datetime import date

from creditcoach import config
from creditcoach.agent import pipeline
from creditcoach.agent.mcp_host import McpHost

EVIDENCE = config.ROOT / "docs" / "evidence" / "week-2" / "task-15-mcp-round-trip.md"
USER = "USR-001"
QUESTION = "Why did my credit score drop 20 points this month, and what's my credit utilization right now?"


class Capture(logging.Handler):
    """Keep the MCP host's log lines (one JSON line per tool call) for the evidence."""

    def __init__(self):
        super().__init__(logging.INFO)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


def listed_tools() -> dict:
    """Ask the MCP server which tools it offers (the same list the host gives the model)."""
    async def go():
        async with McpHost(USER) as host:
            return host.tools
    return asyncio.run(go())


def pct(ratio: float) -> list[str]:
    """Ways a ratio may be written in the answer, e.g. 0.374 -> ["37.4%"], 0.11 -> ["11%", "11.0%"]."""
    whole = f"{ratio * 100:.1f}"
    return [f"{whole}%"] + ([f"{whole[:-2]}%"] if whole.endswith(".0") else [])


def rupees(amount: int) -> str:
    """₹ with Indian digit grouping, e.g. 200000 -> ₹2,00,000."""
    digits = str(amount)
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return "₹" + ",".join(([head] if head else []) + groups + [tail]) if len(digits) > 3 else f"₹{digits}"


def figure_checks(text: str, calls) -> list[tuple[str, str, str, bool]]:
    """Key figures from the tool results, and whether the answer states each one."""
    history = next(c.result for c in calls if c.tool == "get_score_history" and c.ok)
    summary = next(c.result for c in calls if c.tool == "get_account_summary" and c.ok)
    latest, totals = history["points"][-1], summary["totals"]
    worst = max((a for a in summary["accounts"] if a["utilization_ratio"] is not None),
                key=lambda a: a["utilization_ratio"])
    compact = text.replace("−", "-")
    checks = [
        ("Score change this month", f"{latest['change']} ({latest['date'][:7]})", "get_score_history → points[-1].change",
         str(abs(latest["change"])) in compact),
        ("Factor behind it", latest["factor_change"], "get_score_history → points[-1].factor_change",
         all(w in compact.lower() for w in re.findall(r"[a-z]+", latest["factor_change"].lower()) if len(w) > 3)),
        ("Overall utilization", f"{totals['overall_utilization_ratio']}", "get_account_summary → totals.overall_utilization_ratio",
         any(p in compact for p in pct(totals["overall_utilization_ratio"]))),
        ("Card balances total", rupees(totals["revolving_balance_inr"]), "get_account_summary → totals.revolving_balance_inr",
         rupees(totals["revolving_balance_inr"]) in compact),
        ("Card limits total", rupees(totals["revolving_limit_inr"]), "get_account_summary → totals.revolving_limit_inr",
         rupees(totals["revolving_limit_inr"]) in compact),
        (f"Highest-utilization card ({worst['account_id']})",
         f"{rupees(worst['balance_inr'])} ÷ {rupees(worst['credit_limit_inr'])} = {worst['utilization_ratio']}",
         f"get_account_summary → accounts[{worst['account_id']}]",
         rupees(worst["balance_inr"]) in compact and rupees(worst["credit_limit_inr"]) in compact
         and any(p in compact for p in pct(worst["utilization_ratio"]) + ["79%"])),
    ]
    return checks


def main() -> None:
    """Run the live question, check the trace, and write the evidence file."""
    capture = Capture()
    logging.getLogger("creditcoach.agent.mcp_host").addHandler(capture)
    logging.getLogger("creditcoach.agent.mcp_host").setLevel(logging.INFO)
    tools = listed_tools()
    capture.lines.clear()

    a = pipeline.answer(QUESTION, user_id=USER)
    used = {c.tool for c in a.tool_calls if c.ok}
    via_mcp = len(capture.lines) == len(a.tool_calls) and all(c.attempts >= 1 for c in a.tool_calls)
    own_user = all(c.user_id == USER and c.result.get("user_id", USER) == USER for c in a.tool_calls)
    checks = figure_checks(a.text, a.tool_calls) if used == set(tools) else []
    ok = used == set(tools) and via_mcp and own_user and checks and all(c[3] for c in checks)

    mark = lambda good: "✅" if good else "❌"  # noqa: E731
    lines = [
        "# Task 15 Evidence: MCP Round Trip",
        "",
        f"*{date.today().isoformat()} · Code: `creditcoach/tools/server.py` (MCP server), `creditcoach/agent/mcp_host.py` "
        "(MCP host), `creditcoach/agent/pipeline.py` (agent loop) · Tests: `tests/test_mcp.py` · "
        "Script: `uv run python scripts/task15_mcp_round_trip.py`*",
        "",
        "**Definition of Done:** the agent calls both tools via MCP and uses their results in a live response.",
        "",
        "**How a question flows:** retrieve 3 corpus passages → the chat model gets the two tools (without `user_id`) → "
        "for each tool call it makes, the MCP host fills `user_id` from the signed-in session and calls the "
        "CreditCoach MCP server over stdio → each result goes back to the model as a `tool` message → the model "
        "answers from those results.",
        "",
        f"**Result: {'✅ PASS' if ok else '❌ FAIL'}**",
        "",
        "| Check | Result |",
        "|---|---|",
        f"| Both tools called and succeeded | {mark(used == set(tools))} {', '.join(sorted(used)) or 'none'} |",
        f"| Every call went through the MCP server (one host log line per call) | {mark(via_mcp)} "
        f"{len(a.tool_calls)} calls, {len(capture.lines)} log lines |",
        f"| Every call ran for the signed-in user only | {mark(own_user)} {USER} |",
        f"| The answer states the key figures from the tool output | {mark(bool(checks) and all(c[3] for c in checks))} "
        f"{sum(c[3] for c in checks)}/{len(checks)} (table below) |",
        "",
        "## 1. Tools the MCP server lists",
        "",
        "The server's schemas include `user_id`. The host removes it before showing the tools to the model, and "
        "fills it from the session on every call.",
        "",
        "| Tool | Parameters (server) | Parameters the model sees |",
        "|---|---|---|",
        *[f"| `{name}` | {', '.join(f'`{p}`' for p in schema.get('required', []))} | "
          f"{', '.join(f'`{p}`' for p in schema.get('required', []) if p != 'user_id') or '(none)'} |"
          for name, schema in tools.items()],
        "",
        "## 2. The question",
        "",
        f"Signed in as **{USER}** (Aravind). Asked: *\"{QUESTION}\"*",
        "",
        f"Retrieved passages: {', '.join(f'`{p.id}`' for p in a.passages)} ({a.retrieval_seconds:.1f}s).",
        "",
        "## 3. Tool calls, in order",
        "",
        "| # | Tool | Model's arguments | `user_id` (from session) | Result | Attempts | Latency |",
        "|---|---|---|---|---|---|---|",
        *[f"| {i} | `{c.tool}` | `{json.dumps(c.arguments, ensure_ascii=False)}` | {c.user_id} | "
          f"{'ok' if c.ok else c.code} | {c.attempts} | {c.seconds * 1000:.0f} ms |" for i, c in enumerate(a.tool_calls, 1)],
        "",
        "MCP host log (one JSON line per call):",
        "",
        "```",
        *capture.lines,
        "```",
    ]
    for i, c in enumerate(a.tool_calls, 1):
        lines += ["", f"### Call {i}: `{c.tool}` result (sent back to the model)", "", "```json",
                  json.dumps(c.result, indent=2, ensure_ascii=False), "```"]
    lines += [
        "",
        "## 4. The answer",
        "",
        f"*{a.model} · {a.generation_seconds:.1f}s from the end of retrieval to the answer, including tool calls*",
        "",
        *[f"> {line}" if line else ">" for line in a.text.splitlines()],
        "",
        "## 5. Figures in the answer, traced to the tool output",
        "",
        "| Figure | Tool value | Source | In the answer |",
        "|---|---|---|---|",
        *[f"| {name} | {value} | `{source}` | {mark(found)} |" for name, value, source, found in checks],
        "",
        "Any other figure in the answer (for example a paydown target) must be calculated from these values with its "
        "inputs shown, per the system prompt's rule 1.",
        "",
    ]
    EVIDENCE.write_text("\n".join(lines), encoding="utf-8")
    print(pipeline.transcript(a))
    print(f"\n{'PASS' if ok else 'FAIL'}: wrote {EVIDENCE.relative_to(config.ROOT)}")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
