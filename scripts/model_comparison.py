"""Write the dashboard's "Cost against speed and quality" figures from the model-choice runs.

The Docker image leaves ``docs/`` out, so the deployed dashboard can't read the runs. This script reads them here
and writes what it needs to ``creditcoach/evals/model_comparison.json``, which ships with the app:

    rows        One per model and setting (thinking, routing) and benchmark round: how many 50-case runs, cases
                passed (the average, and each run's), median and 90th-percentile seconds over all their answers (the
                90th by nearest rank, as the reports give it), and cost per answer
    runs        Every 50-case run, one line each, for the "every run" list
    screens     The 8-question speed screens (``SCREENS``, and ``OCT_SCREEN`` from persona-test-fixes.md)
    red_team    The red-team runs: attacks held and benign controls passed
    totals      How many runs and answers the choice rests on, and what the benchmark's model calls cost

Cost per answer is the answer model only (its answer and any rewrite; both models for the router). It comes from each
case's recorded ``cost`` (runs since 2026-11-05), else from the case's trace: the local ``.traces/`` files, else
Langfuse. The guardrail reviews are left out and noted on the dashboard. A run most of whose answers came from a
model other than the one under test (a fallback) is listed but kept out of the rows.

Run it after a new run (add it to ``RUNS``), then commit the JSON:

    uv run python scripts/model_comparison.py
"""

import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from creditcoach import config  # noqa: E402
from creditcoach.app import dashboard  # noqa: E402

WEEK4 = ROOT / "docs" / "evidence" / "week-4"
RUNS_DIR = WEEK4 / "runs"
OUT = ROOT / "creditcoach" / "evals" / "model_comparison.json"
TARGET_SECONDS = 15  # the response-time brief: 90% of answers within about 15 s (model-choice-and-caching.md)
BASELINE = "openai/gpt-5"
ROUTER = "router"  # the model key of runs answered through agent.router (Sonnet 5.5 and DeepSeek V4.1 Flash)
# Round 1 chose Sonnet (2026-10-27 to 31); round 2 tested open-weight models and the router (2026-11-05 and 06)
RUNS = ["eval-effort-low", "eval-effort-minimal", "eval-model-claude-sonnet-5-5", "eval-model-gpt-5-6-terra",
        "eval-model-gemini-3-8-flash", "eval-model-claude-haiku-5-5",
        *sorted(p.stem for p in RUNS_DIR.glob("eval-bench-*.json")), *sorted(p.stem for p in RUNS_DIR.glob("eval-router-*.json"))]
SCREENS = RUNS_DIR / "model-benchmark-speed-screen.json"
OCT_SCREEN = [  # persona-test-fixes.md: 8 questions per model, guardrails on, cache off; no per-answer data kept
    ("openai/gpt-5", 20.4, 23.6), ("openai/gpt-5.6-terra", 9.1, 11.4), ("openai/gpt-5.6-luna", 9.8, 12.2),
    ("anthropic/claude-haiku-5.5", 10.7, 14.0), ("google/gemini-3.8-flash", 11.6, 14.0),
    ("anthropic/claude-sonnet-5.5", 13.2, 17.7)]
RED_TEAMS = [ROOT / "docs" / "evidence" / "week-3" / "runs" / "task-21-red-team.json",
             *sorted(RUNS_DIR.glob("red-team-*.json"))]


def setting(run: dict) -> str:
    """How the model was run, in words: "routed", "high thinking", "thinking off" or "default"."""
    if run.get("router") == "on":
        return "routed"
    if run["label"] == "effort-minimal":
        return "minimal thinking"
    if run["label"] == "effort-low":
        return "low thinking"
    thinking = (run.get("benchmark") or {}).get("thinking")
    if not thinking:
        return "default"
    return "thinking off" if thinking.get("enabled") is False else f"{thinking['effort']} thinking"


def rank(values: list[float], q: float) -> float:
    return values[max(0, math.ceil(q * len(values)) - 1)]


def answer_costs(run: dict) -> list[float]:
    """Each case's answer-model cost: recorded with the case, else from its trace."""
    recs = run["records"]
    if all(r.get("cost") for r in recs):
        return [r["cost"]["answer"] for r in recs]
    ids = {r["trace_id"] for r in recs if r.get("trace_id")}
    since = datetime.fromisoformat(run["created"]).replace(tzinfo=UTC) - timedelta(days=1)
    spans = [s for s in dashboard.from_files(since) if s["trace_id"] in ids]
    missing = ids - {s["trace_id"] for s in spans}
    if missing and config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY:
        spans += [s for s in dashboard.from_langfuse(since) if s["trace_id"] in missing]
    return [a["cost"]["answer"] + a["cost"]["rewrite"] for a in dashboard.requests(spans)]


def one(name: str) -> dict:
    run = json.loads((RUNS_DIR / f"{name}.json").read_text(encoding="utf-8"))
    recs = run["records"]
    model = ROUTER if run.get("router") == "on" else run["model"]
    tested = {run["model"], run.get("fast_model")} if model == ROUTER else {run["model"]}
    costs = answer_costs(run)
    return {"label": run["label"], "date": run["created"][:10], "model": model, "setting": setting(run),
            "cases": len(recs), "passed": sum(str(r["pass"]) == "True" for r in recs),
            "seconds": sorted(float(r["seconds"]) for r in recs if r.get("seconds") not in (None, "None")),
            "costs": costs, "valid": sum(r.get("model") in tested for r in recs) > len(recs) / 2}


def grouped(runs: list[dict]) -> list[dict]:
    """One row per model, setting and round, best average score first."""
    groups = defaultdict(list)
    for r in runs:
        if r["valid"]:
            groups[(r["model"], r["setting"], r["date"][:7])].append(r)
    rows = []
    for (model, how, _), rs in groups.items():
        secs = sorted(s for r in rs for s in r["seconds"])
        costs = [c for r in rs for c in r["costs"]]
        rows.append({"model": model, "setting": how, "runs": len(rs), "dates": sorted({r["date"] for r in rs}),
                     "passed": round(statistics.mean(r["passed"] for r in rs), 1),
                     "passed_runs": [r["passed"] for r in rs], "cases": rs[0]["cases"],
                     "median": round(statistics.median(secs), 1), "p90": round(rank(secs, .9), 1),
                     "per_answer": round(statistics.mean(costs), 4) if costs else None, "costed": len(costs)})
    return sorted(rows, key=lambda r: (-r["passed"], r["p90"]))


def screens() -> list[dict]:
    out = [{"date": "2026-10-31", "model": m, "setting": "default", "answers": 8, "median": med, "slowest": slow,
            "per_answer": None} for m, med, slow in OCT_SCREEN]
    for s in json.loads(SCREENS.read_text(encoding="utf-8"))["screens"]:
        secs = sorted(a["seconds"] for a in s["answers"])
        costs = [a["cost"]["answer"] for a in s["answers"] if a.get("cost")]
        thinking = s["thinking"]
        out.append({"date": "2026-11-05", "model": s["model"], "answers": len(secs),
                    "setting": "default" if not thinking else "thinking off" if thinking.get("enabled") is False
                    else f"{thinking['effort']} thinking", "median": round(statistics.median(secs), 1),
                    "slowest": secs[-1], "per_answer": round(statistics.mean(costs), 4) if costs else None})
    return out


def red_teams() -> list[dict]:
    """Attacks held and controls passed per red-team run, scored with Task 21's own checks."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("task21", ROOT / "scripts" / "task21_guardrail_tests.py")
    task21 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(task21)
    out = []
    for path in RED_TEAMS:
        run = json.loads(path.read_text(encoding="utf-8"))
        red = [r for r in run["records"] if r["category"] != "Required"]
        attacks = [r for r in red if r["category"] != "Benign control"]
        controls = [r for r in red if r["category"] == "Benign control"]
        bench = run.get("benchmark") or {}
        out.append({"date": run["created"][:10], "model": bench.get("model") or run["model"],
                    "answers": len(run["records"]),
                    "held": sum(task21.score(r)[0] for r in attacks), "attacks": len(attacks),
                    "controls_passed": sum(task21.score(r)[0] for r in controls), "controls": len(controls)})
    return out


def spend(runs: list[dict]) -> float:
    """What the benchmark's answer models cost, from the per-case costs; judges and guardrail reviews left out."""
    return round(sum(c for r in runs for c in r["costs"]), 2)


def main() -> None:
    runs = [one(name) for name in RUNS]
    rows, scr, red = grouped(runs), screens(), red_teams()
    for r in rows:
        print(f"{r['model']:34} {r['setting']:16} {r['runs']} run(s) {r['passed']}/{r['cases']}  median {r['median']} s  "
              f"90% {r['p90']} s  ${r['per_answer']} per answer")
    totals = {"eval_runs": len(runs), "eval_answers": sum(r["cases"] for r in runs),
              "screens": len(scr), "screen_answers": sum(s["answers"] for s in scr),
              "red_team_runs": len(red), "red_team_answers": sum(r["answers"] for r in red),
              "models": len({r["model"] for r in runs} | {s["model"] for s in scr}) - (ROUTER in {r["model"] for r in runs}),
              "spend": spend(runs), "first": min(r["date"] for r in runs), "last": max(r["date"] for r in runs)}
    print(f"{totals['eval_runs']} eval runs ({totals['eval_answers']} answers), {totals['screens']} screens, "
          f"{totals['red_team_runs']} red-team runs; {totals['models']} models")
    OUT.write_text(json.dumps({
        "target_seconds": TARGET_SECONDS, "baseline": BASELINE, "rows": rows, "totals": totals,
        "runs": [{k: v for k, v in r.items() if k not in ("seconds", "costs")} |
                 {"median": round(statistics.median(r["seconds"]), 1), "p90": round(rank(r["seconds"], .9), 1),
                  "per_answer": round(statistics.mean(r["costs"]), 4) if r["costs"] else None} for r in runs],
        "screens": scr, "red_team": red}, indent=1) + "\n", encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
