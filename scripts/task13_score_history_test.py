"""Task 13: write the test log for the score-history tool.

Definition of Done: the tool returns correct score data points and factor changes for a known period, and a clear
error for an invalid one. This script logs both cases (plus an out-of-range period and a user with no credit file)
with the tool's full output, checks each against the expected figures, checks every figure that the 50
requirements.md queries rely on against the tool (``golden_section``), and appends the pytest run for the
whole test file.

Writes:
    docs/evidence/week-2/task-13-score-history-test.md

Run (no API key needed; results are deterministic):
    uv run python scripts/task13_score_history_test.py
"""

import json
import subprocess
import sys
from datetime import date

from creditcoach import config
from creditcoach.evals import golden
from creditcoach.tools.score_history import get_score_history

EVIDENCE = config.ROOT / "docs" / "evidence" / "week-2" / "task-13-score-history-test.md"

# (title, user_id, period, check on the result, what the check means)
CASES = [
    ("Known period: \"What happened over the last two months?\" (requirements.md §4 #7)",
     "USR-001", "last_2_months",
     lambda r: [(p["score"], p["change"], p["factor_change"]) for p in r["points"]]
     == [(670, -20, "Utilization spike"), (650, -20, "Hard inquiry + utilization spike")]
     and r["summary"]["start_score"] == 690 and r["summary"]["net_change"] == -40,
     "Aug 670 (−20, utilization spike) and Sep 650 (−20, hard inquiry + utilization spike); 690 → 650 is −40, "
     "matching `data/score_history.csv`"),
    ("Known period: \"What was my score in March?\" (§4 #22)",
     "USR-001", "2026-03",
     lambda r: [(p["score"], p["change"], p["factor_change"]) for p in r["points"]] == [(678, 5, "On-time payments")],
     "Mar 2026: 678, +5 from 673, on-time payments"),
    ("Invalid period: wording the tool doesn't accept",
     "USR-001", "last quarter",
     lambda r: r["ok"] is False and r["error"]["code"] == "INVALID_PERIOD" and "points" not in r,
     "Clear `INVALID_PERIOD` error that lists the accepted forms, and no partial data"),
    ("Invalid period: a month that doesn't exist",
     "USR-001", "2026-13",
     lambda r: r["ok"] is False and r["error"]["code"] == "INVALID_PERIOD",
     "Clear `INVALID_PERIOD` error"),
    ("Valid period with no data: \"What was my score in January 2025?\" (§4 #46)",
     "USR-001", "2025-01",
     lambda r: r["ok"] is False and r["error"]["code"] == "PERIOD_OUT_OF_RANGE"
     and r["error"]["details"]["available"] == {"start": "2025-10", "end": "2026-09"},
     "Clear `PERIOD_OUT_OF_RANGE` error naming the months on file, so the agent gives no estimate"),
    ("No credit file (§4 #14)",
     "USR-004", "latest",
     lambda r: r["ok"] is True and r["has_credit_file"] is False and r["points"] == [],
     "A normal result with no points and a note, not an error"),
]


def golden_section(tool: str, call: str) -> tuple[list[str], bool]:
    """Evidence lines checking every get_score_history figure the 50 requirements.md queries rely on, and whether all hold.

    The figures come from ``creditcoach/evals/golden_queries.json`` (the same ones ``tests/test_golden_queries.py``
    checks in CI); each is read from a live tool call here and compared with the expected value.
    """
    rows, ok = [], True
    for q in golden.load():
        for f in (f for f in q.facts if f.tool == tool):
            holds, actual = golden.check_fact(f)
            ok &= holds
            expected = f.equals if f.has_equals else f"no item equals {f.excludes!r}"
            shown = actual if not isinstance(actual, list) or len(actual) <= 3 else f"{len(actual)} items, none matching"
            args = f'"{f.user_id}", "{f.period}"' if f.period else f'"{f.user_id}"'
            rows.append(f"| {q.label} | `{call}({args})` | `{f.path}` | `{expected!r}` | `{shown!r}` | "
                        f"{'✅' if holds else '❌'} |")
    queries = len({r.split(' |')[0] for r in rows})
    lines = ["", f"## All requirements.md figures for this tool ({len(rows)} checks across {queries} queries)", "",
             "Every figure the expected answers in requirements.md §3 and §4 rely on that comes from this tool, read "
             "from a live call. The same checks run in CI as `tests/test_golden_queries.py`.", "",
             f"**Result: {'✅' if ok else '❌'} {sum('✅' in r for r in rows)}/{len(rows)} match.**", "",
             "| Query | Call | Field | Expected | Tool returned | Match |", "|---|---|---|---|---|---|", *rows]
    return lines, ok


def main() -> None:
    """Run the logged cases and the pytest suite, then write the evidence file."""
    results = [(title, uid, period, get_score_history(uid, period), check, meaning)
               for title, uid, period, check, meaning in CASES]
    passed = [check(r) for _, _, _, r, check, _ in results]
    test = subprocess.run([sys.executable, "-m", "pytest", "tests/test_score_history.py", "-v", "--no-header",
                           "-p", "no:cacheprovider"], cwd=config.ROOT, capture_output=True, text=True)
    log = test.stdout.strip().replace(str(config.ROOT) + "/", "")
    golden_lines, golden_ok = golden_section("history", "get_score_history")
    ok = all(passed) and test.returncode == 0 and golden_ok

    lines = [
        "# Task 13 Evidence: Score-History Tool",
        "",
        f"*{date.today().isoformat()} · Code: `creditcoach/tools/score_history.py`, `creditcoach/tools/common.py` · "
        "Tests: `tests/test_score_history.py` · Script: `uv run python scripts/task13_score_history_test.py`*",
        "",
        "**Definition of Done:** returns correct score data points and factor changes for a known period, and a "
        "clear error for an invalid one. The tool follows the spec in [docs/tools.md](../../tools.md) §2.",
        "",
        f"**Result: {'✅ PASS' if ok else '❌ FAIL'}** ({sum(passed)}/{len(passed)} logged cases correct; "
        f"pytest {'passed' if test.returncode == 0 else 'FAILED'}; "
        f"requirements.md figures {'all match' if golden_ok else 'MISMATCH'})",
        "",
        "## Summary",
        "",
        "| # | Case | Call | Expected | Result |",
        "|---|---|---|---|---|",
    ]
    for i, ((title, uid, period, _, _, meaning), good) in enumerate(zip(results, passed), 1):
        lines.append(f"| {i} | {title} | `get_score_history(\"{uid}\", \"{period}\")` | {meaning} | "
                     f"{'✅' if good else '❌'} |")
    for i, (title, uid, period, result, _, _) in enumerate(results, 1):
        lines += ["", f"## {i}. {title}", "", f"`get_score_history(\"{uid}\", \"{period}\")` returned:", "",
                  "```json", json.dumps(result, indent=2, ensure_ascii=False), "```"]
    lines += golden_lines
    lines += ["", "## Test log", "", "`uv run pytest tests/test_score_history.py -v` covers the spec's test cases "
              "T1–T8 and T15 ([docs/tools.md](../../tools.md) §5), every invalid `period` form, clipping, "
              "unknown users, a missing data file, and a cross-check of every user's changes against the CSV.",
              "", "```", log, "```", ""]
    EVIDENCE.write_text("\n".join(lines), encoding="utf-8")
    print(f"{'PASS' if ok else 'FAIL'}: wrote {EVIDENCE.relative_to(config.ROOT)}")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
