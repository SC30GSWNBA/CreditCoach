"""The dashboard (Task 31): tool-call failure rate, guardrail triggers and goal-recall accuracy, from real traces.

A "Dashboard" tab in the chat UI, shown to every signed-in user: the team's logins, people who signed up, and anyone
invited later (since 2026-10-29; until then only the team's logins saw it).
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

Real use is what the chat app answered: traces tagged ``app`` (``observability.set_run``), and before that tag
existed (2026-10-29), traces from the Railway build. Everything else is an eval or test run, listed by run: the eval
harness (``eval:<label>``), the evidence and benchmark scripts (``script:<name>``) and older local traces without a
tag. Until 2026-10-29 only ``eval``-tagged traces counted as test runs, so the scripts' answers were shown as real
use. Under real use, a note says how many answers in the period are eval and test runs instead (2026-10-30), so a
short count isn't read as lost data. The period and the traffic (real use, eval and test runs, or both) are picked
above the dashboard. Only counts are shown: no question, answer or user id leaves this module.
Loaded traces are kept for ``CACHE_SECONDS``, so switching filters doesn't ask Langfuse again.

Example:
    >>> spans, source = load(7)
    >>> summary = summarize(requests(spans), traffic="real")
    >>> summary["tools"]["failed"], summary["goal"]["recalled"]
"""

import base64
import json
import logging
import math
import re
import statistics
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
TRAFFIC = [("Real use", "real"), ("Eval and test runs", "eval"), ("Both", "all")]
UNTAGGED = "local, untagged (before 2026-10-29)"


def run_of(tags: set, env: str) -> str | None:
    """The run an answer belongs to (``eval:baseline``, ``script:task32_edge_cases``, ...), or None for real use."""
    if "eval" in tags:
        return next((t for t in sorted(tags) if t.startswith("eval:")), "eval")
    if "app" in tags or (env == "railway" and "script" not in tags):
        return None
    return next((t for t in sorted(tags) if t.startswith("script:")), UNTAGGED)
SPANS = ("creditcoach.answer", "memory.recall", "guardrail.input", "guardrail.output",  # plus every tool.<name>
         "llm.chat", "agent", "retrieval")  # for cost and speed: model calls, and the steps they sit under
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
    "S5": "Never describe how CreditCoach is built",
}
OUTCOMES = ("passed", "reframed", "blocked")
STEPS = {"model": "Answer model", "tools": "Tools", "check": "Output check", "rewrite": "Rewrites",
         "retrieval": "Retrieval", "input": "Input check"}  # pipeline steps timed for "Where the time goes"
MAX_POINTS = 3000  # answers drawn on the cost vs response time chart, newest first

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
    """A Langfuse observation in the local file's span shape (trace_id, span_id, parent_id, name, start, ms, status,
    env, attributes); Langfuse gives the duration as ``latency`` in seconds."""
    attrs = {k.removeprefix("attributes."): v for k, v in (o.get("metadata") or {}).items()
             if k.startswith("attributes.")}
    if o.get("name") == "creditcoach.answer" and o.get("output") is not None:
        out = o["output"]
        attrs["langfuse.trace.output"] = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
    return {"trace_id": o.get("traceId"), "span_id": o.get("id"), "parent_id": o.get("parentObservationId"),
            "name": o.get("name", ""), "start": o.get("startTime", ""),
            "ms": float(o["latency"]) * 1000 if o.get("latency") is not None else None,
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
    """One record per answer: when, where, which run it came from (None for real use; ``eval`` is True for any run),
    its tool calls, guardrail rules and outcome,
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
        spend = _spend(group)
        for a in answers:
            attrs, text = a["attributes"], str(a["attributes"].get("langfuse.trace.output") or "")
            earlier = bool(goal and goal.get("target_score") and goal.get("session") != attrs.get("session.id"))
            target = str(goal["target_score"]) if earlier else None
            records.append({
                "trace_id": trace_id, "day": a["start"][:10], "env": a.get("env", ""),
                "run": run_of(tags, a.get("env", "")), "eval": run_of(tags, a.get("env", "")) is not None,
                "tools": tools, "rules": rules, "outcome": attrs.get("answer.guardrail") or "passed",
                "goal": earlier, "recalled": bool(target and re.search(rf"\b{target}\b", text)),
                "other_target": bool(target and any(m != target for m in _TARGET.findall(text))
                                     and not re.search(rf"\b{target}\b", text)),
                "seconds": a["ms"] / 1000 if a.get("ms") is not None else _number(attrs.get("answer.seconds")),
                "model": attrs.get("answer.model"), "cache": attrs.get("answer.cache"),
                **spend, "steps": {**spend["steps"], "other": max(0.0, (a.get("ms") or 0) / 1000 - sum(
                    spend["steps"].values())) if a.get("ms") is not None else 0.0},
            })
    return records


def _number(value) -> float:
    """An attribute as a number (Langfuse may hand metadata back as text); 0 if missing or not a number."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _spend(group: list[dict]) -> dict:
    """What one answer's model calls cost and how long each step took, from its trace's spans.

    A model call's role comes from the span it sits under: ``agent`` is the answer model; under ``guardrail.output``
    a call to ``SMALL_MODEL`` is the output check and any other is a rewrite of a reframed answer. Calls anywhere else
    (an eval judge's) aren't the answer's and are left out.
    """
    by_id = {s.get("span_id"): s for s in group if s.get("span_id")}
    cost = {"answer": 0.0, "check": 0.0, "rewrite": 0.0}
    steps = dict.fromkeys(STEPS, 0.0)
    tokens = [0, 0]
    for s in group:
        seconds = (s.get("ms") or 0) / 1000
        if s["name"] == "llm.chat":
            parent = by_id.get(s.get("parent_id"), {}).get("name")
            attrs = s["attributes"]
            if parent == "agent":
                role = "answer"
            elif parent == "guardrail.output":
                role = "check" if attrs.get("gen_ai.response.model") == config.SMALL_MODEL else "rewrite"
            else:
                continue
            cost[role] += _number(attrs.get("gen_ai.usage.cost"))
            steps["model" if role == "answer" else role] += seconds
            tokens[0] += int(_number(attrs.get("gen_ai.usage.input_tokens")))
            tokens[1] += int(_number(attrs.get("gen_ai.usage.output_tokens")))
        elif s["name"].startswith("tool."):
            steps["tools"] += seconds
        elif s["name"] in ("guardrail.input", "retrieval"):
            steps["input" if s["name"] == "guardrail.input" else "retrieval"] += seconds
    return {"cost": cost, "prompt_tokens": tokens[0], "completion_tokens": tokens[1], "steps": steps}


def _rate(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def summarize(records: list[dict], traffic: str = "real") -> dict:
    """The three measures over ``records`` for one kind of traffic: ``"real"``, ``"eval"`` (eval and test runs) or
    ``"all"``."""
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
    hidden = [r for r in records if r not in rs]
    return {
        "answers": len(rs), "where": Counter(r["env"] for r in rs), "runs": Counter(r["run"] for r in rs if r["run"]),
        "elsewhere": {"answers": len(hidden), "untagged": sum(r["run"] == UNTAGGED for r in hidden)}
        if traffic == "real" else None,
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
        "cost": costs(rs),
    }


def rank(values: list[float], p: float) -> float | None:
    """The ``p`` percentile by nearest rank: the value ``p`` of the answers are at or under (as the eval reports)."""
    values = sorted(values)
    return values[max(0, math.ceil(p * len(values)) - 1)] if values else None


def _speed(rs: list[dict]) -> dict:
    """Answers, spend, response time and tokens for a group of answers."""
    secs = [r["seconds"] for r in rs if r.get("seconds")]
    spent = [sum(r["cost"].values()) for r in rs]
    tokens = sum(r["prompt_tokens"] + r["completion_tokens"] for r in rs)
    return {"answers": len(rs), "spend": sum(spent), "per_answer": _rate(sum(spent), len(rs)),
            "per_answer_p95": rank(spent, .95), "p50": statistics.median(secs) if secs else None,
            "p95": rank(secs, .95), "prompt": sum(r["prompt_tokens"] for r in rs),
            "completion": sum(r["completion_tokens"] for r in rs), "tokens_per_answer": _rate(tokens, len(rs)),
            "per_million": _rate(sum(spent) * 1e6, tokens)}


def costs(rs: list[dict]) -> dict:
    """Cost and speed: totals, per answer model, per day, per pipeline step, and the answers to plot."""
    by_model, by_day = defaultdict(list), defaultdict(list)
    for r in rs:
        by_model[r.get("model") or ""].append(r)
        by_day[r["day"]].append(r)
    timed = [r for r in rs if r.get("seconds")]
    days = {}
    for d, day in sorted(by_day.items()):
        spend = Counter()
        for r in day:
            spend[r.get("model") or ""] += r["cost"]["answer"] + r["cost"]["rewrite"]
            spend["check"] += r["cost"]["check"]
        days[d] = {**_speed(day), "by_model": dict(spend)}
    return {
        **_speed(rs),
        "models": {m: _speed(group) for m, group in sorted(by_model.items(), key=lambda kv: -len(kv[1]))},
        "days": days,
        "steps": {k: _rate(sum(r["steps"].get(k, 0) for r in timed), len(timed)) or 0.0 for k in [*STEPS, "other"]},
        "split": {k: sum(r["cost"][k] for r in rs) for k in ("answer", "rewrite", "check")},
        "cache": Counter(r.get("cache") or "unknown" for r in rs),
        "points": [(r["seconds"], sum(r["cost"].values()), r.get("model") or "")
                   for r in sorted(timed, key=lambda r: r["day"], reverse=True)[:MAX_POINTS]],
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
    runs = summary.get("runs") or {}
    runs = (" Eval and test runs: " + ", ".join(f"{escape(k)} {v}" for k, v in runs.most_common()) + ".") if runs else ""
    hidden = summary.get("elsewhere") or {}
    if hidden.get("answers"):  # so a short real-use count isn't read as lost data
        untagged = (f", {hidden['untagged']} of them from this team's machines before 2026-10-29, when traces weren't "
                    "tagged by process yet") if hidden["untagged"] else ""
        runs += (f" Real use is only what the chat app answered: {hidden['answers']} more answers in this period came "
                 f"from eval and test runs{untagged}. Pick \"Eval and test runs\" or \"Both\" to see them.")
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
<p class="cc-note">From {escape(source)}. Answers by where they ran: {where}.{runs}</p>
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


# ---------------------------------------------------------------- cost and speed

VIEWS = [("Quality", "quality"), ("Cost and speed", "cost")]
COST_PARTS = ("top", "scatter", "models", "quality", "quality_table", "spend", "latency", "split", "tokens", "cache")
COMPARISON = Path(__file__).resolve().parents[1] / "evals" / "model_comparison.json"  # scripts/model_comparison.py
# A model keeps its color whatever the period shows; models not listed here are grey
COLORS = {"openai/gpt-5": "#2a78d6", "anthropic/claude-sonnet-5.5": "#eb6834", "google/gemini-3.8-flash": "#1baf7a",
          "openai/gpt-5.6-terra": "#eda100", "anthropic/claude-haiku-5.5": "#e87ba4", "check": "#008300"}
GREY = "#898781"
GRID = "rgba(137, 135, 129, 0.22)"


def model_name(model: str) -> str:
    """A model id as people say it: ``anthropic/claude-sonnet-5.5`` is "Claude Sonnet 5.5", ``openai/gpt-5.6-terra``
    is "GPT-5.6 Terra". An answer with no model call (from the answer cache, or one that failed) has no id."""
    if not model:
        return "No model call"
    if model == "check":
        return f"Output check ({model_name(config.SMALL_MODEL)})"
    parts = model.split("/")[-1].split("-")
    if parts[0] == "gpt" and len(parts) > 1:
        return " ".join([f"GPT-{parts[1]}", *(p.capitalize() for p in parts[2:])])
    return " ".join(p.capitalize() for p in parts)


def _usd(v: float | None, places: int = 4) -> str:
    return "–" if v is None else f"${v:,.{places}f}"


def _secs(v: float | None) -> str:
    return "–" if v is None else f"{v:.1f} s"


def _figure(fig, height: int = 300, **layout):
    """The house style of the charts in this app: transparent, hairline grid (``app.charts``). Text is drawn mid grey
    here and recolored to the page's text color by ``theme.CSS``, so it reads on both themes. The legend says that
    clicking an entry hides or shows it."""
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(color=GREY, size=13), hovermode="closest",
                      legend=dict(orientation="h", y=-0.22, x=0, title_text="Click to hide or show: "), **layout)
    fig.update_xaxes(gridcolor=GRID, zeroline=False, title_font_size=14)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, rangemode="tozero", title_font_size=14)
    return fig


def scatter_figure(c: dict):
    """Cost against response time, one dot per answer, colored by its answer model; a ringed dot is each model's
    median. The legend gives each model's answers, and clicking a model hides it."""
    import plotly.graph_objects as go

    fig = go.Figure()
    points = c["points"]
    for model, m in c["models"].items():
        xs = [p[0] for p in points if p[2] == model]
        if not xs:
            continue
        color = COLORS.get(model, GREY)
        fig.add_trace(go.Scatter(
            x=xs, y=[p[1] for p in points if p[2] == model], mode="markers", legendgroup=model,
            name=f"{model_name(model)} ({m['answers']:,})", marker=dict(color=color, size=6, opacity=.35),
            hovertemplate=f"{escape(model_name(model))}<br>%{{x:.1f}} s · $%{{y:.4f}}<extra></extra>"))
        fig.add_trace(go.Scatter(
            x=[m["p50"]], y=[m["per_answer"]], mode="markers", legendgroup=model, showlegend=False,
            marker=dict(color=color, size=16, line=dict(color="white", width=2.5)),
            hovertemplate=(f"<b>{escape(model_name(model))}</b><br>{m['answers']:,} answers<br>median {_secs(m['p50'])}"
                           f" · p95 {_secs(m['p95'])}<br>{_usd(m['per_answer'])} per answer<extra></extra>")))
    if c["p50"] is not None:
        fig.add_vline(x=c["p50"], line=dict(color=GREY, dash="dot", width=1),
                      annotation_text=f"median {_secs(c['p50'])}", annotation_position="top right")
        fig.add_hline(y=c["per_answer"], line=dict(color=GREY, dash="dot", width=1),
                      annotation_text=f"average {_usd(c['per_answer'])}", annotation_position="top right")
    fig.add_annotation(text=f"<b>{c['answers']:,} answers</b>" + (f" ({len(points):,} newest shown)"
                       if len(points) < c["answers"] else ""), xref="paper", yref="paper", x=0, y=1,
                       showarrow=False, xanchor="left", yanchor="top", font=dict(size=13))
    return _figure(fig, 400, xaxis_title="Response time (seconds)", yaxis_title="Cost per answer (US$)",
                   yaxis_tickprefix="$")


def _by_day(c: dict, value) -> tuple[list[str], list]:
    days = sorted(c["days"])
    return days, [value(c["days"][d]) for d in days]


def spend_figure(c: dict):
    """Spend per day, stacked by answer model, with the output check apart."""
    import plotly.graph_objects as go

    fig = go.Figure()
    for model in [*c["models"], "check"]:
        days, ys = _by_day(c, lambda d, m=model: d["by_model"].get(m, 0))
        if any(ys):
            fig.add_trace(go.Bar(x=days, y=ys, name=model_name(model), marker_color=COLORS.get(model, GREY),
                                 hovertemplate=f"%{{x}} · {escape(model_name(model))}<br>$%{{y:.3f}}<extra></extra>"))
    return _figure(fig, barmode="stack", bargap=.35, yaxis_tickprefix="$", xaxis_type="date")


def latency_figure(c: dict):
    """The typical (p50) and slowest one-in-twenty (p95) response time per day, on one axis."""
    import plotly.graph_objects as go

    fig = go.Figure()
    for key, label, color in (("p50", "p50, the typical answer", COLORS["openai/gpt-5"]),
                              ("p95", "p95, the slowest one in twenty", COLORS["anthropic/claude-sonnet-5.5"])):
        days, ys = _by_day(c, lambda d, k=key: d[k])
        fig.add_trace(go.Scatter(x=days, y=ys, name=label, mode="lines+markers", line=dict(color=color, width=2),
                                 marker=dict(size=8), hovertemplate=f"%{{x}} · {key} %{{y:.1f}} s<extra></extra>"))
    return _figure(fig, yaxis_ticksuffix=" s", xaxis_type="date")


def tokens_figure(c: dict):
    """Prompt and completion tokens per day."""
    import plotly.graph_objects as go

    fig = go.Figure()
    for key, label, color in (("prompt", "Prompt", COLORS["openai/gpt-5"]),
                              ("completion", "Completion", COLORS["anthropic/claude-sonnet-5.5"])):
        days, ys = _by_day(c, lambda d, k=key: d[k])
        fig.add_trace(go.Bar(x=days, y=ys, name=label, marker_color=color,
                             hovertemplate=f"%{{x}} · {label}<br>%{{y:,}} tokens<extra></extra>"))
    return _figure(fig, barmode="stack", bargap=.35, xaxis_type="date")


def comparison() -> dict | None:
    """The 50-case eval runs per model (``model_comparison.json``), or None if the file is missing or unreadable."""
    try:
        return json.loads(COMPARISON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.warning("No model comparison at %s", COMPARISON)
        return None


def quality_figure(cmp: dict):
    """Eval cases passed against the time 90% of answers came within; dot size is cost per answer, and the shaded
    side of the dashed line meets the response-time target."""
    import plotly.graph_objects as go

    target, top = cmp["target_seconds"], max(r["per_answer"] or 0 for r in cmp["rows"]) or 1
    rightmost = max(r["p90"] for r in cmp["rows"])
    fig = go.Figure()
    fig.add_vrect(x0=0, x1=target, fillcolor="rgba(79, 70, 229, .08)", line_width=0)
    fig.add_vline(x=target, line=dict(color="#4f46e5", dash="dash", width=1.5),
                  annotation_text=f"{target} s target", annotation_position="bottom left")
    for r in cmp["rows"]:
        tag = " (current)" if r["model"] == config.CHAT_MODEL else ""
        fig.add_trace(go.Scatter(
            x=[r["p90"]], y=[r["passed"]], mode="markers+text", showlegend=False,
            text=[f"{model_name(r['model'])}{tag} · {_usd(r['per_answer'])}"],
            textposition="middle left" if r["p90"] == rightmost else "middle right",
            textfont=dict(size=13), marker=dict(color=COLORS.get(r["model"], GREY), line=dict(color="white", width=2),
                                                size=12 + 18 * ((r["per_answer"] or 0) / top) ** .5),
            hovertemplate=(f"<b>{escape(model_name(r['model']))}</b><br>{r['passed']}/{r['cases']} passed<br>median "
                           f"{r['median']} s · 90% within {r['p90']} s<br>{_usd(r['per_answer'])} per answer"
                           "<extra></extra>")))
    ys = [r["passed"] for r in cmp["rows"]]
    return _figure(fig, 340, xaxis_title="90% of answers within (seconds)", xaxis_ticksuffix=" s",
                   yaxis_title=f"Eval cases passed (of {cmp['rows'][0]['cases']})",
                   yaxis_range=[min(ys) - 2, max(ys) + 2], yaxis_rangemode="normal",
                   xaxis_range=[0, rightmost * 1.12])


def _cells(head: list[str], rows: list[list[str]]) -> str:
    """A table whose cells are HTML already (escaped by the caller)."""
    th = "".join(f"<th>{escape(h)}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f'<div class="cc-dash-scroll"><table class="cc-dash-table cc-num"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def _swatch(model: str) -> str:
    return f'<i class="cc-sw" style="background:{COLORS.get(model, GREY)}"></i>'


def _model_cell(model: str) -> str:
    pill = '<span class="cc-pill-now">Current</span>' if model == config.CHAT_MODEL else ""
    return f"{_swatch(model)}{escape(model_name(model))}{pill}"


def models_html(c: dict) -> str:
    """"Models compared": each answer model in the period, the best value in each column marked."""
    rows = {m: v for m, v in c["models"].items() if m}
    cols = [("answers", "Answers", lambda v: f"{v:,}", None), ("p50", "p50", _secs, min), ("p95", "p95", _secs, min),
            ("per_answer", "Cost per answer", _usd, min),
            ("per_answer", "Per 1,000 answers", lambda v: _usd(None if v is None else v * 1000, 2), min),
            ("tokens_per_answer", "Tokens per answer", lambda v: "–" if v is None else f"{v:,.0f}", min),
            ("per_million", "Per 1M tokens", lambda v: _usd(v, 2), min)]
    best = {k: pick(v[k] for v in rows.values() if v[k] is not None) for k, _, _, pick in cols
            if pick and len(rows) > 1 and any(v[k] is not None for v in rows.values())}
    table = _cells(["Model", *(label for _, label, _, _ in cols)],
                   [[_model_cell(m), *(f'<span class="{"cc-best" if k in best and v[k] == best[k] else ""}">'
                                       f'{fmt(v[k])}</span>' for k, _, fmt, _ in cols)] for m, v in rows.items()])
    none = c["models"].get("")
    note = (f'<p class="cc-note">Not in the table: {none["answers"]} answers with no model call (from the answer cache,'
            " or failed before the model answered).</p>") if none else ""
    return ('<h3>Models compared</h3><p class="cc-note">Every answer model in this period. The best value in each '
            "column is in green. Cost per 1,000 answers is the figure to budget with.</p>"
            + (table if rows else '<p class="cc-note">No answers in this period.</p>') + note)


def quality_html(cmp: dict | None) -> str:
    """The table under "Cost against speed and quality"."""
    if not cmp:
        return '<p class="cc-note">The model comparison isn\'t available on this copy of CreditCoach.</p>'
    base = next((r["per_answer"] for r in cmp["rows"] if r["model"] == cmp["baseline"]), None)
    rows, target = cmp["rows"], cmp["target_seconds"]
    hi, fast = max(r["passed"] for r in rows), min(r["p90"] for r in rows)
    cheap = min(r["per_answer"] for r in rows if r["per_answer"] is not None)
    table = _cells(["Model", "Passed", "Median", "90% within", "Cost per answer", f"vs {model_name(cmp['baseline'])}",
                    "Per 1,000 questions"],
                   [[_model_cell(r["model"]),
                     f'<span class="{"cc-best" if r["passed"] == hi else ""}">{r["passed"]}/{r["cases"]}</span>',
                     _secs(r["median"]),
                     f'<span class="{"cc-best" if r["p90"] == fast else ""}">{_secs(r["p90"])}</span>'
                     + (' <span class="cc-note">over target</span>' if r["p90"] > target else ""),
                     f'<span class="{"cc-best" if r["per_answer"] == cheap else ""}">{_usd(r["per_answer"])}</span>',
                     f"{r['per_answer'] / base:.1f}×" if base and r["per_answer"] is not None else "–",
                     f"~${r['per_answer'] * 1000:,.0f}" if r["per_answer"] is not None else "–"] for r in rows])
    meets = [r for r in rows if r["passed"] == hi and r["p90"] <= target]
    insight = (f"{' and '.join(model_name(r['model']) for r in meets)} "
               f"{'is the only model with' if len(meets) == 1 else 'are the models with'} the top score "
               f"({hi}/{rows[0]['cases']}) and 90% of answers within {target} s." if meets else "")
    runs = ", ".join(sorted({r["date"] for r in rows}))
    return (table + f'<p class="cc-note">From the 50-case eval runs ({escape(runs)}). Cost is the answer model only; '
            "the guardrail reviews add about $0.0003 per question on top.</p>"
            + (f'<p class="cc-insight">{escape(insight)}</p>' if insight else ""))


def _stack(parts: list[tuple[str, float, str]], fmt) -> str:
    """A bar split into parts, with a key giving each part's value."""
    total = sum(v for _, v, _ in parts) or 1
    bar = "".join(f'<i style="flex:{v:.6f};background:{color}" title="{escape(label)}: {fmt(v)} ({v / total:.0%})"></i>'
                  for label, v, color in parts if v > 0)
    keys = "".join(f'<div><i class="cc-sw" style="background:{color}"></i>{escape(label)}<b>{fmt(v)}</b></div>'
                   for label, v, color in parts)
    return f'<div class="cc-stack">{bar}</div><div class="cc-keys">{keys}</div>'


def split_html(c: dict) -> str:
    """"Where the time goes" and "Where the money goes"."""
    steps, colors = c["steps"], ["#2a78d6", "#1baf7a", "#008300", "#e87ba4", "#eda100", "#6250d6", GREY]
    total = sum(steps.values())
    time_parts = [(label, steps[k], colors[i]) for i, (k, label) in enumerate([*STEPS.items(), ("other", "Other")])]
    split = c["split"]
    money = [("Answer model", split["answer"], "#2a78d6"), ("Rewrites", split["rewrite"], "#e87ba4"),
             ("Output check", split["check"], "#008300")]
    spend = sum(split.values())
    time_note = (f"The answer model takes {steps['model'] / total:.0%} of the wait; the output check adds "
                 f"{steps['check']:.1f} s.") if total else ""
    money_note = f"The output check is {split['check'] / spend:.0%} of spend." if spend else ""
    return f"""<div class="cc-dash-grid">
  <div><h3>Where the time goes</h3><p class="cc-note">Average seconds per answer, by pipeline step
    ({total:.1f} s in all).</p>{_stack(time_parts, lambda v: f"{v:.2f} s")}
    {f'<p class="cc-insight">{time_note}</p>' if time_note else ""}</div>
  <div><h3>Where the money goes</h3><p class="cc-note">Spend by pipeline step. Retrieval, the guardrail rules and the
    tools run without a model call.</p>{_stack(money, lambda v: _usd(v, 2))}
    {f'<p class="cc-insight">{money_note}</p>' if money_note else ""}</div>
</div>"""


def cache_html(c: dict) -> str:
    """How often a saved answer was used instead of a model call, and the prompt's share of tokens."""
    cache, tokens = c["cache"], c["prompt"] + c["completion"]
    looked = cache.get("hit", 0) + cache.get("miss", 0)
    share = f"{c['prompt'] / tokens:.0%}" if tokens else "–"
    rows = [("Answer cache hits", f"{cache.get('hit', 0)} of {looked} lookups"),
            ("Answers with the cache off", f"{cache.get('off', 0)} of {c['answers']}"),
            ("Prompt share of tokens", share)]
    return ('<h3>Caching</h3><p class="cc-note">How often a saved answer was used instead of calling the model.</p>'
            '<div class="cc-keys cc-keys-1">' + "".join(f"<div>{k}<b>{v}</b></div>" for k, v in rows) + "</div>"
            + ('<p class="cc-insight">Most tokens are prompt (the instructions, retrieved passages and the user\'s data),'
               " so prompt length drives cost more than answer length.</p>" if tokens and c["prompt"] / tokens > .5
               else ""))


def top_html(c: dict, source: str, period: str, traffic: str) -> str:
    """The tiles, and where the figures come from."""
    tokens = c["prompt"] + c["completion"]
    tiles = [("Spend", _usd(c["spend"], 2), f"{c['answers']:,} answers · model calls only"),
             ("Cost per answer", _usd(c["per_answer"]),
              f"p95 {_usd(c['per_answer_p95'])} · {_usd(None if c['per_answer'] is None else c['per_answer'] * 1000, 2)}"
              " per 1,000"),
             ("Response time", f"{_secs(c['p50'])} <small>p50</small>", f"p95 {_secs(c['p95'])}: the slowest one in twenty"),
             ("Tokens", f"{tokens / 1e6:.2f}M" if tokens >= 1e5 else f"{tokens:,}",
              f"{c['prompt'] / tokens:.0%} prompt · {c['tokens_per_answer']:,.0f} per answer" if tokens else "none"),
             ("Cost per 1M tokens", _usd(c["per_million"], 2), "across every model call")]
    return ('<div class="cc-tiles">' + "".join(
        f'<div class="cc-tile"><span class="cc-k">{k}</span><span class="cc-v">{v}</span><span class="cc-n">{n}</span>'
        "</div>" for k, v, n in tiles) + "</div>"
        + f'<p class="cc-note">{escape(traffic)} · {escape(period.lower())}. From {escape(source)}. Cost is what '
        "OpenRouter reported for each model call; eval judges' calls are left out.</p>")


def cost_view(days: int, traffic: str) -> dict:
    """Every part of the "Cost and speed" view (``COST_PARTS``) for a period and a traffic kind: HTML or a Plotly
    figure each. If the traces can't be read, the first part says so and the rest are empty."""
    period = next((label for label, d in PERIODS if d == days), f"Last {days} days")
    kind = next((label for label, k in TRAFFIC if k == traffic), traffic)
    cmp = comparison()
    try:
        spans, source = load(days)
        c = summarize(requests(spans), traffic)["cost"]
    except Exception:
        log.exception("Cost and speed unavailable")
        return {**dict.fromkeys(COST_PARTS), "top": ('<div class="cc-empty"><b>Cost and speed are unavailable right '
                                                     'now.</b><p class="cc-note">Press Refresh to try again.</p></div>')}
    return {"top": top_html(c, source, period, kind), "scatter": scatter_figure(c), "models": models_html(c),
            "quality": quality_figure(cmp) if cmp else None, "quality_table": quality_html(cmp),
            "spend": spend_figure(c), "latency": latency_figure(c), "split": split_html(c),
            "tokens": tokens_figure(c), "cache": cache_html(c)}


CSS = """
.cc-dash-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(560px, 100%), 1fr)); gap: 16px; }
.cc-dash-grid > div { min-width: 0; overflow-x: auto; }
.cc-dash-table { width: 100%; border-collapse: collapse; font-size: .86rem; font-variant-numeric: tabular-nums; }
.cc-dash-table th, .cc-dash-table td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border-color-primary);
  overflow-wrap: break-word; }
.cc-dash-table th { color: var(--body-text-color-subdued); font-weight: 500; }
.cc-dash-scroll { overflow-x: auto; }
.cc-num td, .cc-num th { white-space: nowrap; }
.cc-num td:not(:first-child), .cc-num th:not(:first-child) { text-align: right; }
.cc-best { color: #0ca30c; font-weight: 700; }
.cc-sw { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; }
.cc-pill-now { font-size: .7rem; font-weight: 700; padding: 1px 7px; border-radius: 999px; margin-left: 6px;
  background: rgba(79, 70, 229, .14); color: #4f46e5; }
.cc-insight { font-size: .86rem; border-left: 3px solid var(--border-color-primary); padding-left: 10px; margin-top: 8px; }
.cc-stack { display: flex; gap: 2px; height: 24px; border-radius: 6px; overflow: hidden; margin: 8px 0 10px; }
.cc-stack i { display: block; height: 100%; }
.cc-keys { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 6px 16px; font-size: .86rem; }
.cc-keys > div { display: flex; gap: 6px; align-items: baseline; }
.cc-keys b { margin-left: auto; font-variant-numeric: tabular-nums; white-space: nowrap; }
.cc-keys-1 { grid-template-columns: 1fr; max-width: 420px; }
"""
