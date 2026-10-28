"""The team dashboard (Task 31): tool-call failure rate, guardrail triggers and goal-recall accuracy, from real traces.

A "Dashboard" tab in the chat UI, shown only to the team's logins (``auth.is_team``), never to people who signed up.
It reads the traces every answer already leaves (Task 26) and computes three measures over a chosen period:

    Measure                  From                                    Counted as
    Tool-call failure rate   every ``tool.<name>`` span              calls with ``tool.ok`` false (or ERROR status),
                                                                     over all calls; per tool, with the error codes
    Guardrail triggers       ``guardrail.input`` / ``guardrail.output``   every rule in ``guardrail.rules`` (one per
                                                                     finding), per rule; and how each answer left the
                                                                     guardrail layer (``answer.guardrail``)
    Goal-recall accuracy     ``memory.recall`` + ``creditcoach.answer``   answers given while a goal from an earlier
                                                                     session was stored that name its target score,
                                                                     over all such answers (the check sample row #3
                                                                     uses); answers naming a different target are
                                                                     counted apart

Where the traces come from:
    Langfuse     When its keys are set: ``GET /api/public/v2/observations`` for the period, so answers from every
                 machine, Railway included, are counted. Langfuse's ``attributes.*`` metadata is turned back into
                 the span attributes the local file holds, so both sources feed the same functions.
    Local files  Otherwise, or when Langfuse can't be reached: ``.traces/*.jsonl`` from this machine only.

Eval runs (traces tagged ``eval``) are kept apart from real use; the period and the traffic (real use, eval runs or
both) are picked above the dashboard. Only counts are shown: no question, answer or user id leaves this module.
Loaded traces are kept for ``CACHE_SECONDS``, so switching filters doesn't ask Langfuse again.

Example:
    >>> spans, source = load(7)
    >>> summary = summarize(requests(spans), traffic="real")
    >>> summary["tools"]["failed"], summary["goal"]["recalled"]
"""

import base64
import json
import logging
import re
import threading
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path

from creditcoach import config

log = logging.getLogger(__name__)

PERIODS = [("Last 24 hours", 1), ("Last 7 days", 7), ("Last 30 days", 30)]
TRAFFIC = [("Real use", "real"), ("Eval runs", "eval"), ("Both", "all")]
SPANS = ("creditcoach.answer", "memory.recall", "guardrail.input", "guardrail.output")  # plus every tool.<name>
CACHE_SECONDS = 60
MAX_PAGES = 20  # 1,000 observations a page: a bound on one load, far above a month of team use

RULES = {  # docs/guardrails.md
    "G1": "Never guarantee a score outcome or timeline",
    "G2": "Never endorse a predatory product",
    "G3": "Never fabricate a credit figure",
    "S1": "Keep its rules when told to ignore them",
    "S2": "Never reveal its system prompt",
    "S3": "Never ask for, repeat or store personal identifiers",
    "S4": "Only discuss the signed-in user's data",
}
OUTCOMES = ("passed", "reframed", "blocked")

# A target score the answer attributes to the user's goal ("your target of 750", "aiming for 750").
_TARGET = re.compile(r"(?:target|goal|aim(?:ing)? for|aiming at)\D{0,25}?\b([3-8]\d{2}|900)\b", re.I)

_cache: dict = {}
_cache_lock = threading.Lock()


# ---------------------------------------------------------------- loading

def _langfuse_get(path: str, **query) -> dict:
    """One GET to the Langfuse public API with the project's keys."""
    auth = base64.b64encode(f"{config.LANGFUSE_PUBLIC_KEY}:{config.LANGFUSE_SECRET_KEY}".encode()).decode()
    url = config.LANGFUSE_HOST.rstrip("/") + path + "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v})
    request = urllib.request.Request(url, headers={"Authorization": f"Basic {auth}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _from_observation(o: dict) -> dict:
    """A Langfuse observation in the local file's span shape (trace_id, name, start, status, env, attributes)."""
    attrs = {k.removeprefix("attributes."): v for k, v in (o.get("metadata") or {}).items()
             if k.startswith("attributes.")}
    if o.get("name") == "creditcoach.answer" and o.get("output") is not None:
        out = o["output"]
        attrs["langfuse.trace.output"] = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
    return {"trace_id": o.get("traceId"), "name": o.get("name", ""), "start": o.get("startTime", ""),
            "status": "ERROR" if o.get("level") == "ERROR" else "OK", "env": o.get("environment") or "default",
            "attributes": attrs}


def from_langfuse(since: datetime) -> list[dict]:
    """Every span the dashboard needs since ``since``, from Langfuse. Raises if Langfuse can't be read."""
    spans = []
    queries = [{"name": n, "fields": "core,basic,metadata" + (",io" if n == "creditcoach.answer" else "")}
               for n in SPANS] + [{"type": "TOOL", "fields": "core,basic,metadata"}]
    for q in queries:
        cursor = None
        for _ in range(MAX_PAGES):
            page = _langfuse_get("/api/public/v2/observations", limit=1000, cursor=cursor,
                                 fromStartTime=since.strftime("%Y-%m-%dT%H:%M:%SZ"), **q)
            spans += [_from_observation(o) for o in page.get("data", [])]
            cursor = (page.get("meta") or {}).get("cursor")
            if not cursor or not page.get("data"):
                break
    return spans


def from_files(since: datetime, folder: Path | None = None) -> list[dict]:
    """Every span the dashboard needs since ``since``, from this machine's ``.traces/<UTC date>.jsonl`` files."""
    folder = Path(folder or config.TRACES_DIR)
    spans = []
    for path in sorted(folder.glob("*.jsonl")):
        if path.stem < since.strftime("%Y-%m-%d"):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    s = json.loads(line)
                except json.JSONDecodeError:  # a line cut short by a crash
                    continue
                if (s.get("name") in SPANS or s.get("name", "").startswith("tool.")) and s["start"] >= since.isoformat():
                    spans.append({**s, "env": "this machine"})
    return spans


def load(days: int, now: datetime | None = None) -> tuple[list[dict], str]:
    """The spans of the last ``days`` days and where they came from: Langfuse when its keys are set, else (or if
    Langfuse fails) the local files. Kept for ``CACHE_SECONDS``."""
    now = now or datetime.now(UTC)
    since = now - timedelta(days=days)
    with _cache_lock:
        hit = _cache.get(days)
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1], hit[2]
    if config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY:
        try:
            spans, source = from_langfuse(since), f"Langfuse ({config.LANGFUSE_HOST}): every machine that sends it traces"
        except Exception as exc:
            log.warning("Dashboard couldn't read Langfuse (%s); using local trace files", exc)
            spans, source = from_files(since), f"local trace files (Langfuse unreachable: {type(exc).__name__})"
    else:
        spans, source = from_files(since), "local trace files on this machine (no Langfuse keys)"
    with _cache_lock:
        _cache[days] = (time.monotonic(), spans, source)
    return spans, source


def forget() -> None:
    """Drop the loaded traces, so the next ``load`` reads them afresh (the Refresh button)."""
    with _cache_lock:
        _cache.clear()


# ---------------------------------------------------------------- measuring

def _goal(value) -> dict | None:
    """The stored goal from a ``memory.recall`` span (JSON text, or a dict), or None.

    Langfuse cuts long metadata strings, usually inside ``quote``, so when the JSON doesn't parse the two fields
    the dashboard needs are read from the text: ``target_score`` and ``session`` come before ``quote``.
    """
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            score, session = re.search(r'"target_score": (\d+)', value), re.search(r'"session": "([^"]+)"', value)
            return {"target_score": int(score[1]), "session": session and session[1]} if score else None
    return value if isinstance(value, dict) else None


def requests(spans: list[dict]) -> list[dict]:
    """One record per answer: when, where, whether it was an eval run, its tool calls, guardrail rules and outcome,
    and whether it recalled the stored goal. Traces without a ``creditcoach.answer`` span are left out."""
    by_trace = defaultdict(list)
    for s in spans:
        by_trace[s["trace_id"]].append(s)
    records = []
    for trace_id, group in by_trace.items():
        answers = [s for s in group if s["name"] == "creditcoach.answer"]
        if not answers:
            continue
        tags = {t for s in group for t in (s["attributes"].get("langfuse.trace.tags") or [])}
        tools = [{"tool": s["attributes"].get("tool.name") or s["name"].removeprefix("tool."),
                  "ok": s["attributes"].get("tool.ok") is not False and s.get("status") != "ERROR",
                  "code": s["attributes"].get("tool.code")} for s in group if s["name"].startswith("tool.")]
        rules = [r for s in group if s["name"] in ("guardrail.input", "guardrail.output")
                 for r in (s["attributes"].get("guardrail.rules") or [])]
        goal = next((_goal(s["attributes"].get("memory.goal")) for s in group if s["name"] == "memory.recall"), None)
        for a in answers:
            attrs, text = a["attributes"], str(a["attributes"].get("langfuse.trace.output") or "")
            earlier = bool(goal and goal.get("target_score") and goal.get("session") != attrs.get("session.id"))
            target = str(goal["target_score"]) if earlier else None
            records.append({
                "trace_id": trace_id, "day": a["start"][:10], "env": a.get("env", ""), "eval": "eval" in tags,
                "tools": tools, "rules": rules, "outcome": attrs.get("answer.guardrail") or "passed",
                "goal": earlier, "recalled": bool(target and re.search(rf"\b{target}\b", text)),
                "other_target": bool(target and any(m != target for m in _TARGET.findall(text))
                                     and not re.search(rf"\b{target}\b", text)),
            })
    return records


def _rate(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def summarize(records: list[dict], traffic: str = "real") -> dict:
    """The three measures over ``records`` for one kind of traffic: ``"real"``, ``"eval"`` or ``"all"``."""
    rs = [r for r in records if traffic == "all" or r["eval"] == (traffic == "eval")]
    calls = [c for r in rs for c in r["tools"]]
    per_tool = defaultdict(lambda: {"calls": 0, "failed": 0, "codes": Counter()})
    for c in calls:
        t = per_tool[c["tool"]]
        t["calls"] += 1
        if not c["ok"]:
            t["failed"] += 1
            t["codes"][c["code"] or "ERROR"] += 1
    failed = sum(not c["ok"] for c in calls)
    rules = Counter(rule for r in rs for rule in r["rules"])
    with_goal = [r for r in rs if r["goal"]]
    days = defaultdict(list)
    for r in rs:
        days[r["day"]].append(r)
    return {
        "answers": len(rs), "where": Counter(r["env"] for r in rs),
        "tools": {"calls": len(calls), "failed": failed, "rate": _rate(failed, len(calls)),
                  "answers_hit": sum(any(not c["ok"] for c in r["tools"]) for r in rs),
                  "per_tool": dict(sorted(per_tool.items()))},
        "guardrails": {"triggers": sum(rules.values()), "per_rule": dict(sorted(rules.items())),
                       "answers_hit": sum(bool(r["rules"]) for r in rs),
                       "outcomes": {o: sum(r["outcome"] == o for r in rs) for o in OUTCOMES}},
        "goal": {"answers": len(with_goal), "recalled": sum(r["recalled"] for r in with_goal),
                 "other_target": sum(r["other_target"] for r in with_goal),
                 "rate": _rate(sum(r["recalled"] for r in with_goal), len(with_goal))},
        "days": [{"day": d, "answers": len(day),
                  "tool_rate": _rate(sum(not c["ok"] for r in day for c in r["tools"]),
                                     sum(len(r["tools"]) for r in day)),
                  "triggers": sum(len(r["rules"]) for r in day),
                  "goal": f"{sum(r['recalled'] for r in day if r['goal'])} of {sum(r['goal'] for r in day)}"}
                 for d, day in sorted(days.items(), reverse=True)],
    }


# ---------------------------------------------------------------- showing

def _pct(r: float | None) -> str:
    return "–" if r is None else f"{r * 100:.1f}".removesuffix(".0") + "%"


def _table(head: list[str], rows: list[list], empty: str) -> str:
    if not rows:
        return f'<p class="cc-note">{escape(empty)}</p>'
    th = "".join(f"<th>{escape(h)}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{escape(str(c))}</td>" for c in row) + "</tr>" for row in rows)
    return f'<table class="cc-dash-table"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'


def html(summary: dict, source: str, period: str, traffic: str) -> str:
    """The dashboard: three tiles, then a table per measure and one per day."""
    t, g, m = summary["tools"], summary["guardrails"], summary["goal"]
    outcomes = g["outcomes"]
    where = ", ".join(f"{escape(k)} {v}" for k, v in summary["where"].most_common()) or "none"
    tiles = f"""<div class="cc-tiles">
  <div class="cc-tile"><span class="cc-k">Answers</span><span class="cc-v">{summary["answers"]}</span>
    <span class="cc-n">{escape(traffic)} · {escape(period.lower())}</span></div>
  <div class="cc-tile"><span class="cc-k">Tool-call failure rate</span><span class="cc-v">{_pct(t["rate"])}</span>
    <span class="cc-n">{t["failed"]} of {t["calls"]} calls failed · {t["answers_hit"]} answers affected</span></div>
  <div class="cc-tile"><span class="cc-k">Guardrail triggers</span><span class="cc-v">{g["triggers"]}</span>
    <span class="cc-n">in {g["answers_hit"]} answers · {outcomes["reframed"]} reframed, {outcomes["blocked"]} blocked</span></div>
  <div class="cc-tile"><span class="cc-k">Goal-recall accuracy</span><span class="cc-v">{_pct(m["rate"])}</span>
    <span class="cc-n">{m["recalled"]} of {m["answers"]} answers with a stored goal named its target{
        f' · {m["other_target"]} named a different one' if m["other_target"] else ""}</span></div>
</div>"""
    tools = _table(["Tool", "Calls", "Failed", "Failure rate", "Error codes"],
                   [[name, v["calls"], v["failed"], _pct(_rate(v["failed"], v["calls"])),
                     ", ".join(f"{c} ×{n}" for c, n in v["codes"].most_common()) or "–"]
                    for name, v in t["per_tool"].items()], "No tool calls in this period.")
    rules = _table(["Rule", "What it guards", "Triggers"],
                   [[rule, RULES.get(rule, ""), n] for rule, n in g["per_rule"].items()],
                   "No guardrail triggered in this period.")
    days = _table(["Day (UTC)", "Answers", "Tool-call failure rate", "Guardrail triggers", "Goal recalled"],
                  [[d["day"], d["answers"], _pct(d["tool_rate"]), d["triggers"], d["goal"]] for d in summary["days"]],
                  "No answers in this period.")
    return f"""{tiles}
<p class="cc-note">From {escape(source)}. Answers by where they ran: {where}.</p>
<div class="cc-dash-grid">
  <div><h3>Tool calls</h3>{tools}</div>
  <div><h3>Guardrail triggers</h3>{rules}
    <p class="cc-note">How answers left the guardrail layer: {outcomes["passed"]} passed, {outcomes["reframed"]} reframed,
    {outcomes["blocked"]} blocked.</p></div>
</div>
<h3>Goal recall</h3>
<p class="cc-note">Counted on answers given while a goal from an earlier session was stored: recalled when the answer
names the stored target score, as sample row #3 is checked. Questions the goal doesn't affect count too, so real use
reads lower than the eval's goal cases.</p>
<h3>By day</h3>{days}"""


def view(days: int, traffic: str) -> str:
    """The dashboard HTML for a period (in days) and a traffic kind, or a short note if the traces can't be read."""
    period = next((label for label, d in PERIODS if d == days), f"Last {days} days")
    kind = next((label for label, k in TRAFFIC if k == traffic), traffic)
    try:
        spans, source = load(days)
        return html(summarize(requests(spans), traffic), source, period, kind)
    except Exception:
        log.exception("Dashboard unavailable")
        return ('<div class="cc-empty"><b>The dashboard is unavailable right now.</b>'
                '<p class="cc-note">Press Refresh to try again. The chat still works.</p></div>')


CSS = """
.cc-dash-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(560px, 100%), 1fr)); gap: 16px; }
.cc-dash-grid > div { min-width: 0; overflow-x: auto; }
.cc-dash-table { width: 100%; border-collapse: collapse; font-size: .86rem; font-variant-numeric: tabular-nums; }
.cc-dash-table th, .cc-dash-table td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border-color-primary);
  overflow-wrap: break-word; }
.cc-dash-table th { color: var(--body-text-color-subdued); font-weight: 500; }
"""
