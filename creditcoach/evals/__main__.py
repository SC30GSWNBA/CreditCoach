"""Run the eval harness (Task 27): ``uv run python -m creditcoach.evals [--all] [--label NAME] [--rescore | --rejudge | --compare BEFORE]``.

See ``creditcoach.evals.harness`` for the cases, the scorers and what is written. Exits 1 if any case fails.
"""

import argparse
import sys

from creditcoach.evals import harness


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m creditcoach.evals", description="Run the eval harness (Task 27).")
    parser.add_argument("--all", action="store_true", help="also run the 44 additional queries (requirements.md §4)")
    parser.add_argument("--label", default="latest", help="name of the run, used in the file names (default: latest)")
    redo = parser.add_mutually_exclusive_group()
    redo.add_argument("--rescore", action="store_true", help="score the saved run again, with no model calls")
    redo.add_argument("--rejudge", action="store_true", help="judge the saved answers again, then score them")
    redo.add_argument("--compare", metavar="BEFORE", help="write the before/after report of run BEFORE vs --label")
    args = parser.parse_args()
    if args.compare:
        print(f"wrote {harness.compare(args.compare, args.label).relative_to(harness.config.ROOT)}")
        return 0
    if args.rescore or args.rejudge:
        result = harness.rescore(args.label, rejudge=args.rejudge)
    else:
        result = harness.run(args.label, everything=args.all)
    report, _ = harness.paths(args.label)
    for r in result["records"]:
        failed = [f"{s['name']}: {s['detail']}" for s in r["scores"] if not s["passed"]]
        print(f"{'PASS' if r['pass'] else 'FAIL'} {r['label']:8} {r['seconds']:5.1f}s" + (" | " + " | ".join(failed) if failed else ""))
    s = harness.summary(result)["all"]
    print(f"Score: {s['passed']}/{s['cases']} ({s['score']:.0%}); wrote {report.relative_to(harness.config.ROOT)}")
    return 0 if s["passed"] == s["cases"] else 1


if __name__ == "__main__":
    sys.exit(main())
