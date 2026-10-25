"""Task 26: run one live request and export its trace, with every event tied to a single trace ID.

Definition of Done: every event for one request shares a single trace ID. Evidence: an exported trace for one
request showing all event types tied together.

The request is the payday-loan question (requirements.md §3 #4), asked as USR-001 the way the chat UI asks it: with an
open memory session, the cache on and the guardrail layer on. ``get_account_summary`` is made to time out through the
MCP host's real timeout path (as in the Week 2 query #45 run), so the trace has a tool failure as well as a successful
tool call, retrieval with the product-risk passages, a guardrail trigger (G2: a predatory product is mentioned), every
model call, and every cache lookup.

The cache is a fresh in-process store, so the run neither reads nor changes Redis and the injected failure can't be
hidden by a cached account summary. Memory goes to a temporary folder, never the shared Neon database.

Every span emitted during the run is captured, so the check covers spans outside the request too: there must be none.

Writes:
    docs/evidence/week-4/task-26-trace.md          the trace as a span tree and an event timeline, with the checks
    docs/evidence/week-4/runs/task-26-trace.json   the exported trace: every span with its attributes and events
    .traces/<UTC date>.jsonl                       the same spans, as the app writes them (git-ignored)
    Langfuse                                       also, when LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set

Run (needs OPENROUTER_API_KEY and the vector store; one GPT-5 answer and one SMALL_MODEL review):
    uv run python scripts/task26_trace_export.py
"""

import json
import sys
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from creditcoach import cache, config
from creditcoach import observability as obs
from creditcoach.agent import pipeline
from creditcoach.cache.backend import MemoryBackend
from creditcoach.evals.live import FAULT_TOOL, TimingOutAccounts

WEEK = config.ROOT / "docs" / "evidence" / "week-4"
EVIDENCE = WEEK / "task-26-trace.md"
EXPORT = WEEK / "runs" / "task-26-trace.json"
USER_ID = "USR-001"
QUESTION = "Should I take out this payday loan to pay off my credit card?"
REQUIRED = [  # (event type in tasks.md, how it shows in the trace, test on the exported spans)
    ("Retrieval", "`retrieval` span with the passages and scores",
     lambda spans, events: any(s["name"] == "retrieval" and s["attributes"].get("retrieval.passages") for s in spans)),
    ("Tool call", "`tool.<name>` span, OK status",
     lambda spans, events: any(s["name"].startswith("tool.") and s["attributes"].get("tool.ok") for s in spans)),
    ("Guardrail trigger", "`guardrail.trigger` event with the rule",
     lambda spans, events: any(e["name"] == "guardrail.trigger" for _, e in events)),
    ("Tool failure", "`tool.<name>` span with ERROR status and a `tool.failure` event",
     lambda spans, events: any(e["name"] == "tool.failure" for _, e in events)
     and any(s["name"].startswith("tool.") and s["status"] == "ERROR" for s in spans)),
]
ALSO = [  # recorded too, beyond the four the task names
    ("Model call", "`llm.chat` span: model, tokens, cost",
     lambda spans, events: any(s["name"] == "llm.chat" for s in spans)),
    ("Cache lookup", "`cache` event on the span that looked",
     lambda spans, events: any(e["name"] == "cache" for _, e in events)),
    ("Memory recall", "`memory.recall` span: stored goal, earlier sessions",
     lambda spans, events: any(s["name"] == "memory.recall" for s in spans)),
]


def tree(spans: list[dict]) -> list[str]:
    """The spans as an indented tree in start order, each with its duration, status and key facts."""
    children: dict[str | None, list[dict]] = {}
    for s in sorted(spans, key=lambda s: s["start"]):
        children.setdefault(s["parent_id"], []).append(s)
    t0 = min(s["start"] for s in spans)
    lines = []

    def facts(s: dict) -> str:
        a = s["attributes"]
        keep = {"retrieval": ["retrieval.passages"], "llm.chat": ["gen_ai.response.model", "gen_ai.usage.input_tokens",
                                                                  "gen_ai.usage.output_tokens", "gen_ai.usage.cost"],
                "guardrail.input": ["guardrail.rules", "guardrail.products"],
                "guardrail.output": ["guardrail.action", "guardrail.reviewed"],
                "memory.recall": ["memory.sessions"], "cache.answer": ["cache.result", "cache.reason"],
                "creditcoach.answer": ["user.id", "answer.guardrail", "answer.cache", "answer.tool_failures"]}
        names = keep.get(s["name"], ["tool.ok", "tool.code", "tool.attempts", "tool.cached"]
                         if s["name"].startswith("tool.") else [])
        shown = [f"{n.split('.', 1)[-1]}={a[n]}" for n in names if n in a]
        return ", ".join(shown)

    def walk(parent: str | None, depth: int) -> None:
        for s in children.get(parent, []):
            offset = (datetime.fromisoformat(s["start"]) - datetime.fromisoformat(t0)).total_seconds() * 1000
            status = " **ERROR**" if s["status"] == "ERROR" else ""
            events = f" · {len(s['events'])} event{'s' if len(s['events']) != 1 else ''}" if s["events"] else ""
            detail = f" · {facts(s)}" if facts(s) else ""
            lines.append(f"{'    ' * depth}{s['name']}  [+{offset:,.0f} ms, {s['ms']:,.0f} ms]{status}{events}{detail}")
            walk(s["span_id"], depth + 1)
    walk(None, 0)
    return lines


def timeline(spans: list[dict]) -> list[tuple[dict, dict]]:
    """Every event of every span, in time order, as (span, event)."""
    out = []
    for s in spans:
        start = datetime.fromisoformat(s["start"])
        out += [(s, {**e, "at": start.timestamp() * 1000 + e["ms"]}) for e in s["events"]]
    return sorted(out, key=lambda pair: pair[1]["at"])


def describe(e: dict) -> str:
    a = e["attributes"]
    if e["name"] == "cache":
        return f"{a.get('layer')}: {a.get('result')}" + (f" ({a['reason']})" if a.get("reason") else "")
    if e["name"] == "guardrail.trigger":
        return f"{a.get('rule')} at {a.get('stage')}: {a.get('detail')} {list(a.get('matched', []))}"
    if e["name"] in ("tool.failure", "tool.retry"):
        return f"{a.get('tool', '')} {a.get('code')}: {a.get('message', 'retrying once')}".strip()
    return json.dumps(a, ensure_ascii=False)[:160]


def main() -> None:
    config.MEMORY_DIR = Path(tempfile.mkdtemp(prefix="creditcoach-task26-")) / "memory"
    config.MEMORY_BACKEND = "files"  # never the shared Neon database
    config.TRACES = "on"
    from creditcoach.memory import store

    provider = obs.configure()  # the app's own exporters: .traces/ and, if configured, Langfuse
    captured = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(captured))  # everything emitted during the run, for the check
    remote = "Langfuse" if config.LANGFUSE_PUBLIC_KEY else "OTLP collector" if config.OTLP_ENDPOINT else None

    cache.use(MemoryBackend())
    pipeline.retrieve("warm up the embedding and reranker models")  # outside any trace; model loading isn't the point
    captured.clear()
    session = store.start_session(USER_ID, source="evidence")
    pipeline.McpHost = TimingOutAccounts
    print(f"Asking as {USER_ID} with {FAULT_TOOL} timing out: {QUESTION}", flush=True)
    a = pipeline.answer(QUESTION, user_id=USER_ID, session=session, use_cache=True)
    obs.flush()

    emitted = [obs.as_dict(s) for s in captured.get_finished_spans()]
    spans = obs.load(a.trace_id)
    events = timeline(spans)
    one_trace = {s["trace_id"] for s in emitted} == {a.trace_id}
    in_file = sorted(s["span_id"] for s in spans) == sorted(s["span_id"] for s in emitted)
    roots = [s for s in spans if s["parent_id"] is None]
    results = [(name, how, test(spans, events)) for name, how, test in REQUIRED + ALSO]
    ok = one_trace and in_file and len(roots) == 1 and all(r[2] for r in results[:len(REQUIRED)])

    WEEK.joinpath("runs").mkdir(parents=True, exist_ok=True)
    EXPORT.write_text(json.dumps({"trace_id": a.trace_id, "exported": datetime.now(UTC).isoformat(timespec="seconds"),
                                  "user_id": USER_ID, "question": QUESTION, "fault": f"{FAULT_TOOL} times out",
                                  "spans": spans}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    counts: dict[str, int] = {}
    for s in spans:
        kind = "tool.*" if s["name"].startswith("tool.") else s["name"]
        counts[kind] = counts.get(kind, 0) + 1
    root = roots[0]["attributes"] if roots else {}
    model_calls = [s for s in spans if s["name"] == "llm.chat"]
    cost = sum(s["attributes"].get("gen_ai.usage.cost", 0) for s in model_calls)
    lines = ["# Task 26 Evidence: One Request, One Trace", "",
             f"*{date.today().isoformat()} · Code: `creditcoach/observability.py`, wired into "
             "`creditcoach/agent/pipeline.py`, `creditcoach/agent/mcp_host.py`, `creditcoach/llm.py`, "
             "`creditcoach/guardrails/rails.py`, `creditcoach/cache/__init__.py` · Tests: `tests/test_observability.py` "
             "· Script: `uv run python scripts/task26_trace_export.py`*", "",
             "**Definition of Done:** every event for one request shares a single trace ID.", "",
             f"**Result: {'✅ PASS' if ok else '❌ FAIL'}**", "",
             f"Trace ID: **`{a.trace_id}`** · exported trace: [runs/task-26-trace.json](runs/task-26-trace.json) "
             f"({len(spans)} spans, {len(events)} events)", "",
             f"The request: *\"{QUESTION}\"*, asked as {USER_ID} with an open memory session, the cache on and the "
             f"guardrail layer on, as the chat UI asks it. `{FAULT_TOOL}` was made to time out through the MCP host's "
             "real timeout path, so one request carries both a successful tool call and a failed one. Every span was "
             "recorded with OpenTelemetry and written to `.traces/` as the app writes it"
             + (f", and sent to {remote}." if remote else "; no Langfuse keys were set for this run, so it went "
                "only to the local file."), "",
             "## Checks", "",
             "| Check | Result |", "|---|---|",
             f"| Every span emitted during the run belongs to trace `{a.trace_id[:8]}…` | "
             f"{'✅' if one_trace else '❌'} {len(emitted)} of {len(emitted)} spans |"
             if one_trace else f"| Every span emitted during the run belongs to one trace | ❌ "
             f"{len({s['trace_id'] for s in emitted})} trace IDs |",
             f"| The exported file holds all of them | {'✅' if in_file else '❌'} {len(spans)} spans |",
             f"| One root span (`creditcoach.answer`); every other span hangs under it | "
             f"{'✅' if len(roots) == 1 else '❌'} {len(roots)} root |",
             *(f"| {name}: {how} | {'✅' if passed else '❌'} |" for name, how, passed in results[:len(REQUIRED)]),
             "", "Also in the same trace:", "",
             *(f"- {'✅' if passed else '❌'} {name}: {how}" for name, how, passed in results[len(REQUIRED):]),
             "", "## Span tree", "",
             "Each line is one span: when it started after the request began, how long it took, its status, and "
             "the attributes that matter most. The full attributes are in the exported JSON.", "",
             "```", *tree(spans), "```", "",
             "## Event timeline", "",
             "Every event in the trace, in order, with the span it belongs to. All carry the same trace ID.", "",
             "| # | Event | Span | Detail |", "|---|---|---|---|",
             *(f"| {i} | `{e['name']}` | `{s['name']}` | {describe(e).replace('|', '/')} |"
               for i, (s, e) in enumerate(events, 1)), "",
             "## What the request did", "",
             f"- Spans by kind: " + ", ".join(f"{k} {v}" for k, v in counts.items()),
             f"- Model calls: {len(model_calls)}, together ${cost:.4f} "
             f"({', '.join(s['attributes'].get('gen_ai.response.model', '?') for s in model_calls)})",
             f"- Guardrail: {root.get('answer.guardrail')} · answer cache: {root.get('answer.cache')} · "
             f"tool failures: {root.get('answer.tool_failures')} · {root.get('answer.seconds')} s in all", "",
             "The answer the user saw:", "", *[f"> {line}" if line else ">" for line in a.text.splitlines()], ""]
    EVIDENCE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{'PASS' if ok else 'FAIL'}: trace {a.trace_id}, {len(spans)} spans; wrote "
          f"{EVIDENCE.relative_to(config.ROOT)} and {EXPORT.relative_to(config.ROOT)}"
          + (f"; also sent to {remote}" if remote else ""))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
