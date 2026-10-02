"""Run the 50 golden queries through the live pipeline and save every answer, for Tasks 5, 10 and 15.

Two modes, matching how the pipeline has grown:
    tools     As the chat UI does since Task 15: signed in as each query's user, with both tools over MCP. Query
              #45 runs with ``get_account_summary`` forced to time out in the MCP host (the real timeout path),
              so the graceful-degradation answer is exercised.
    no-tools  As the Task 10 prototype: no user and no tools, so answers rest on the corpus alone.

Each query is a single turn in a fresh session with no memory. Memory exists since Tasks 16-17, but this runner
doesn't seed a stored goal or an earlier session yet (Task 27, docs/memory.md §9), so queries that depend on them are
run as asked and their records carry the golden ``needs`` list. ``scripts/task17_goal_recall.py`` covers them live.

A run is saved as JSON (one record per query: the answer, model, passages, every tool call with its result, timings,
and any exception), so later scripts can re-score it without paying for new model calls: the Task 5 prompt-rule
checks read the tools-mode run.

Example:
    >>> from creditcoach.evals import live
    >>> records = live.run("tools", ids=[1, 2])      # 2 live queries; needs OPENROUTER_API_KEY
"""

import json
import os
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from creditcoach.agent import pipeline
from creditcoach.agent.mcp_host import McpHost
from creditcoach.evals import golden

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")  # the tokenizer's own threads don't mix with ours
FAULT_TOOL = "get_account_summary"
_RETRIEVAL_LOCK = threading.Lock()


class TimingOutAccounts(McpHost):
    """An MCP host whose ``get_account_summary`` calls always time out, through the host's real timeout path."""

    async def _send(self, name: str, args: dict) -> dict:
        if name != FAULT_TOOL:
            return await super()._send(name, args)
        saved, self.timeout = self.timeout, 1e-6  # no MCP round trip finishes in a microsecond
        try:
            return await super()._send(name, args)
        finally:
            self.timeout = saved


def _record(q: golden.Query, mode: str, a: pipeline.Answer | None, error: str | None, seconds: float) -> dict:
    """One saved result: the query, the answer and everything needed to re-check it."""
    rec = {"id": q.id, "user_id": q.user_id if mode == "tools" else None, "query": q.query, "mode": mode,
           "fault": q.fault if mode == "tools" else None, "needs": q.needs, "seconds": round(seconds, 1),
           "error": error, "answer": None, "model": None, "passages": [], "tool_calls": []}
    if a:
        rec.update(answer=a.text, model=a.model, retrieval_seconds=round(a.retrieval_seconds, 1),
                   generation_seconds=round(a.generation_seconds, 1),
                   passages=[{"id": p.id, "category": p.category, "score": p.score, "text": p.text} for p in a.passages],
                   tool_calls=[{**asdict(c), "ok": c.ok, "code": c.code, "seconds": round(c.seconds, 3)}
                               for c in a.tool_calls])
    return rec


def _ask(q: golden.Query, mode: str) -> dict:
    """Answer one golden query in the given mode, never raising (an exception is saved in the record)."""
    start = time.perf_counter()
    try:
        a = pipeline.answer(q.query, user_id=q.user_id if mode == "tools" else None)
        return _record(q, mode, a, None, time.perf_counter() - start)
    except Exception:  # a crash is a finding to report, not a reason to lose the other 49 answers
        return _record(q, mode, None, traceback.format_exc(limit=3), time.perf_counter() - start)


def run(mode: str, ids: list[int] | None = None, workers: int = 4) -> list[dict]:
    """Run golden queries live and return one record per query, ordered by query number.

    Args:
        mode: "tools" or "no-tools".
        ids: Query numbers to run (default: all 50).
        workers: Queries answered at once. Each runs its own MCP server process.

    Returns:
        The saved records (see ``_record``).
    """
    if mode not in ("tools", "no-tools"):
        raise ValueError(f"unknown mode {mode!r}")
    queries = [q for q in golden.load() if ids is None or q.id in ids]
    retrieve = pipeline.retrieve
    retrieve("warm up the embedding and reranker models")  # load once, before threads share them

    def one_at_a_time(*args, **kwargs):
        # The embedding model, reranker and Chroma client aren't safe to call from several threads at once (a
        # parallel run segfaulted), so retrieval runs serially; model and tool calls still overlap.
        with _RETRIEVAL_LOCK:
            return retrieve(*args, **kwargs)

    normal = [q for q in queries if not (mode == "tools" and q.fault)]
    pipeline.retrieve = one_at_a_time
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            records = list(pool.map(lambda q: _ask(q, mode), normal))
    finally:
        pipeline.retrieve = retrieve
    for q in (q for q in queries if mode == "tools" and q.fault):  # one at a time: the fault patches the pipeline
        original, pipeline.McpHost = pipeline.McpHost, TimingOutAccounts
        try:
            records.append(_ask(q, mode))
        finally:
            pipeline.McpHost = original
    return sorted(records, key=lambda r: r["id"])


def save(records: list[dict], path: Path, **meta) -> None:
    """Write a run to JSON with when and how it was made."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"created": datetime.now().isoformat(timespec="seconds"), **meta, "records": records},
                               indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def load_run(path: Path) -> dict:
    """Read a run saved by ``save``."""
    return json.loads(path.read_text(encoding="utf-8"))


class _Call:
    """A saved tool call with the attributes ``golden.check_answer`` reads."""

    def __init__(self, d: dict):
        self.tool, self.ok, self.code, self.result = d["tool"], d["ok"], d["code"], d["result"]


def check(rec: dict) -> golden.AnswerCheck:
    """Re-run the golden answer checks on a saved record."""
    q = golden.by_id()[rec["id"]]
    tools = [_Call(c) for c in rec["tool_calls"]] if rec["mode"] == "tools" else None
    if tools is not None and rec["fault"]:
        tools = None  # the injected failure is the point of the query; the answer checks cover its handling
    return golden.check_answer(q, rec["answer"] or "", tools, with_data=rec["mode"] == "tools")


def sources(rec: dict) -> str:
    """Everything an answer's figures may come from: the question, the passages and the tool results."""
    return "\n".join([rec["query"], *(p["text"] for p in rec["passages"]),
                      *(json.dumps(c["result"], ensure_ascii=False) for c in rec["tool_calls"])])


def status(rec: dict, chk: golden.AnswerCheck) -> str:
    """Short result label: crashed, failed, passed, or passed with parts deferred to later tasks."""
    if rec["error"] or not rec["answer"]:
        return "💥 error"
    if not chk.ok:
        return "❌ fail"
    return "⏸ pass, partly deferred" if rec["needs"] else "✅ pass"
