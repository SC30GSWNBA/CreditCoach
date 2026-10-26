"""Run the eval harness (Task 27): ``uv run python -m creditcoach.evals [--all] [--label NAME] [--rescore]``.

See ``creditcoach.evals.harness`` for the cases, the scorers and what is written. Exits 1 if any case fails.
"""

import argparse
import sys

from creditcoach.evals import harness


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m creditcoach.evals", description="Run the eval harness (Task 27).")
    parser.add_argument("--all", action="store_true", help="also run the 44 additional queries (requirements.md §4)")
    parser.add_argument("--label", default="latest", help="name of the run, used in the file names (default: latest)")
    parser.add_argument("--rescore", action="store_true", help="score the saved run again, with no model calls")
    args = parser.parse_args()
    result = harness.rescore(args.label) if args.rescore else harness.run(args.label, everything=args.all)
    report, _ = harness.paths(args.label)
    for r in result["records"]:
        failed = [f"{s['name']}: {s['detail']}" for s in r["scores"] if not s["passed"]]
        print(f"{'PASS' if r['pass'] else 'FAIL'} {r['label']:8} {r['seconds']:5.1f}s" + (" | " + " | ".join(failed) if failed else ""))
    s = harness.summary(result)["all"]
    print(f"Score: {s['passed']}/{s['cases']} ({s['score']:.0%}); wrote {report.relative_to(harness.config.ROOT)}")
    return 0 if s["passed"] == s["cases"] else 1


if __name__ == "__main__":
    sys.exit(main())
