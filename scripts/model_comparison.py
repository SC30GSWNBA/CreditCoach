"""Write the dashboard's "Cost against speed and quality" table from the 50-case eval runs.

The Docker image leaves ``docs/`` out, so the deployed dashboard can't read the eval runs. This script reads them
here and writes the few figures it needs to ``creditcoach/evals/model_comparison.json``, which ships with the app:

    Passed           cases passed, from the run's records
    Median, 90%      seconds per answer from the records; the 90th percentile by nearest rank, as the reports give it
    Cost per answer  the answer model only (its answer and any rewrite), from each case's trace: the local
                     ``.traces/`` files, else Langfuse. The guardrail reviews are left out and noted on the dashboard

Run it after a new model's eval run (add the run to ``RUNS``), then commit the JSON:

    uv run python scripts/model_comparison.py
"""

import json
import statistics
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from creditcoach import config  # noqa: E402
from creditcoach.app import dashboard  # noqa: E402

RUNS_DIR = ROOT / "docs" / "evidence" / "week-4" / "runs"
OUT = ROOT / "creditcoach" / "evals" / "model_comparison.json"
RUNS = ["eval-effort-low", "eval-model-claude-sonnet-5-5", "eval-model-gpt-5-6-terra", "eval-model-gemini-3-8-flash",
        "eval-model-claude-haiku-5-5"]  # the first is the baseline the others are compared with ("vs GPT-5")
TARGET_SECONDS = 15  # the response-time brief: 90% of answers within about 15 s (model-choice-and-caching.md)


def spans_for(trace_ids: set[str], since: datetime) -> list[dict]:
    """The spans of these traces: from the local files, then Langfuse for any trace not found there."""
    spans = [s for s in dashboard.from_files(since) if s["trace_id"] in trace_ids]
    missing = trace_ids - {s["trace_id"] for s in spans}
    if missing and config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY:
        spans += [s for s in dashboard.from_langfuse(since) if s["trace_id"] in missing]
    return spans


def row(name: str) -> dict:
    run = json.loads((RUNS_DIR / f"{name}.json").read_text(encoding="utf-8"))
    records = run["records"]
    seconds = sorted(float(r["seconds"]) for r in records if r.get("seconds") not in (None, "None"))
    ids = {r["trace_id"] for r in records if r.get("trace_id")}
    created = datetime.fromisoformat(run["created"]).replace(tzinfo=UTC)
    answers = dashboard.requests(spans_for(ids, created - timedelta(days=1)))
    main = [a["cost"]["answer"] + a["cost"]["rewrite"] for a in answers]
    return {"model": run["model"], "run": run["label"], "date": run["created"][:10], "cases": len(records),
            "passed": sum(str(r["pass"]) == "True" for r in records),
            "median": round(statistics.median(seconds), 1), "p90": round(dashboard.rank(seconds, .9), 1),
            "per_answer": round(sum(main) / len(main), 4) if main else None, "costed": len(main)}


def main() -> None:
    rows = [row(name) for name in RUNS]
    for r in rows:
        print(f"{r['model']:32} {r['passed']}/{r['cases']}  median {r['median']} s  90% {r['p90']} s  "
              f"${r['per_answer']} per answer ({r['costed']} of {r['cases']} answers costed)")
    OUT.write_text(json.dumps({"target_seconds": TARGET_SECONDS, "baseline": rows[0]["model"], "rows": rows},
                              indent=1) + "\n", encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
