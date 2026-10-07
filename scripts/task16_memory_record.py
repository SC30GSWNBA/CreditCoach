"""Task 16: write one memory record, read it back, and log both as evidence.

Definition of Done: the memory schema is documented (docs/memory.md) and a record can be written and read back
correctly. This script works in a temporary memory folder (nothing reaches the shared ``memory/``) and logs:

    1. Goal record   Session 1 stores Aravind's goal from requirements.md §3 #5 as a ``goal_set`` event; the raw
                     line is shown, then a separate session reads it back with ``store.load``, and every field is
                     compared. A change to 750 (§4 #38) shows the previous goal kept with it.
    2. Validation    Invalid goals are refused with a clear reason (out-of-range score, bad date, no user words).
    3. Dreaming      (--live, one SMALL_MODEL call) Two sessions are consolidated into a dream; the evidence shows
                     what was kept, what the validator rejected, and that the goal didn't change.

Writes:
    docs/evidence/week-2/task-16-memory-record.md

Run:
    uv run python scripts/task16_memory_record.py          # no API key needed
    uv run python scripts/task16_memory_record.py --live   # adds the dreaming run (one paid SMALL_MODEL call)
"""

import argparse
import json
import sys
import tempfile
from dataclasses import asdict
from datetime import date
from pathlib import Path

from creditcoach import config

EVIDENCE = config.ROOT / "docs" / "evidence" / "week-2" / "task-16-memory-record.md"
GOAL = {"target_score": 720, "target_date": "2027-09", "purpose": "buy a car"}
QUOTE = "Remember that I'm saving for a car and want to hit a 720 score by next year."


def main() -> None:
    parser = argparse.ArgumentParser(description="Task 16 evidence: write and read back a memory record.")
    parser.add_argument("--live", action="store_true", help="also run one dreaming pass (paid SMALL_MODEL call)")
    args = parser.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="creditcoach-task16-")) / "memory"
    config.MEMORY_DIR = tmp  # everything below writes to a throwaway folder
    config.MEMORY_BACKEND = "files"  # never the shared Neon database
    from creditcoach.memory import dream, store

    checks = []

    def check(name, ok, detail):
        checks.append((name, bool(ok), detail))

    # 1. Write in session 1, read back from a fresh load (as session 2 would).
    s1 = store.start_session("USR-001", source="evidence")
    store.record(s1, "user_message", QUOTE)
    written = store.set_goal(s1, GOAL, quote=QUOTE)
    store.record(s1, "assistant_message", "Saved: a 720 score by September 2027, to buy a car.")
    store.record(s1, "logout")
    raw = [json.loads(l) for l in s1.path.read_text(encoding="utf-8").splitlines()]
    goal_line = next(l for l in raw if l["type"] == "goal_set")

    s2 = store.start_session("USR-001", source="evidence")
    read = store.load("USR-001").goal
    for f in ("target_score", "target_date", "purpose", "quote", "session", "set_at"):
        check(f"Read back `{f}`", getattr(read, f) == getattr(written, f), f"`{getattr(read, f)!r}`")
    check("Read back from a different session than the one that wrote it", s2.session != read.session,
          f"written in {read.session}, read in {s2.session}")

    store.record(s2, "user_message", "Actually, change my target to 750.")
    changed = store.set_goal(s2, {**GOAL, "target_score": 750}, quote="Actually, change my target to 750.")
    m = store.load("USR-001")
    change_line = json.loads(s2.path.read_text(encoding="utf-8").splitlines()[-1])
    check("A change keeps the purpose and date and records the previous goal (§4 #38)",
          m.goal == changed and change_line["meta"]["previous"]["target_score"] == 720
          and (m.goal.purpose, m.goal.target_date) == ("buy a car", "2027-09"),
          f"720 → {m.goal.target_score}; history {[g.target_score for g in m.goal_history]}")
    check("Another user's memory is empty", store.load("USR-002").goal is None and not store.load("USR-002").episodes,
          "USR-002: no goal, no episodes")

    # 2. Validation.
    refusals = []
    for bad, quote in [({"target_score": 950}, QUOTE), ({"target_date": "next year"}, QUOTE),
                       ({"lender": "X", "target_score": 720}, QUOTE), (GOAL, "")]:
        try:
            store.set_goal(s2, bad, quote=quote)
            refusals.append((bad, quote, "❌ accepted"))
        except store.MemoryRecordError as exc:
            refusals.append((bad, quote, f"✅ refused: {exc}"))
    check("Invalid goals are refused", all(r[2].startswith("✅") for r in refusals), f"{len(refusals)} cases")

    # 3. Dreaming (live).
    dream_lines = []
    if args.live:
        s3 = store.start_session("USR-001", source="evidence")
        for role, text in [("user_message", "Keep it short please. I'm getting married in March 2027 and want a car "
                                             "before that. My score is 650 right now, right?"),
                           ("assistant_message", "Yes, 650 as of Sep 2026. Paying ACC-01 below 30% is the fastest lever."),
                           ("user_message", "Should I aim for 800 instead?"),
                           ("assistant_message", "800 is possible over time; your saved goal stays 750 unless you "
                                                 "confirm a change.")]:
            store.record(s3, role, text)
        store.record(s3, "logout")
        before = store.load("USR-001").goal
        d = dream.dream("USR-001")
        after = store.load("USR-001").goal
        check("Dreaming ran and wrote a new dream file", d is not None and len(d["covers"]) == 3,
              f"{d['model'] if d else 'none'}; covers {len(d['covers']) if d else 0} sessions")
        check("Dreaming didn't change the goal (§4 #40: 'Should I aim for 800?')", before == after,
              f"goal stays {after.target_score}")
        check("No credit figure stored as a fact or preference",
              d and not any(dream.FIGURE.search(i["text"]) for i in d["semantic"]["facts"] + d["procedural"]["preferences"]),
              f"{len(d['semantic']['facts'])} facts, {len(d['procedural']['preferences'])} preferences")
        dream_lines = ["", "## 3. Dreaming: consolidating the sessions (live)", "",
                       "A third session adds a preference, a life event, a score question and a \"should I aim for "
                       "800?\" question. Dreaming then consolidates all three sessions with "
                       f"`{config.SMALL_MODEL}`. The dream file it wrote:", "",
                       "```json", json.dumps(d, indent=1, ensure_ascii=False), "```"]

    ok = all(c[1] for c in checks)
    lines = [
        "# Task 16 Evidence: Memory Record Written and Read Back", "",
        f"*{date.today().isoformat()} · Schema: [docs/memory.md](../../memory.md) · Code: `creditcoach/memory/store.py`, "
        "`creditcoach/memory/dream.py` · Tests: `tests/test_memory.py` · Script: "
        f"`uv run python scripts/task16_memory_record.py{' --live' if args.live else ''}`*", "",
        "**Definition of Done:** schema documented; a record can be written and read back correctly.", "",
        "The script uses a temporary memory folder, so these sessions aren't added to the shared `memory/`.", "",
        f"**Result: {'✅ PASS' if ok else '❌ FAIL'}** ({sum(c[1] for c in checks)}/{len(checks)} checks)", "",
        "| Check | Result | Detail |", "|---|---|---|",
        *[f"| {n} | {'✅' if good else '❌'} | {d} |" for n, good, d in checks], "",
        "## 1. The record written (requirements.md §3 #5)", "",
        f"Session `{s1.session}`, signed in as USR-001 (Aravind). The user says: *\"{QUOTE}\"*", "",
        f"The `goal_set` line appended to `memory/USR-001/episodes/{s1.path.name}`:", "",
        "```json", json.dumps(goal_line, ensure_ascii=False), "```", "",
        "The whole episode file:", "", "```json", *[json.dumps(l, ensure_ascii=False) for l in raw], "```", "",
        f"## 2. The record read back (session `{s2.session}`)", "",
        "`store.load(\"USR-001\").goal` before the change:", "",
        "```python", repr(read), "```", "",
        "After *\"Actually, change my target to 750.\"* (§4 #38), the new line keeps the previous goal:", "",
        "```json", json.dumps(change_line, ensure_ascii=False), "```", "",
        "### Invalid goals", "", "| Goal | Quote | Result |", "|---|---|---|",
        *[f"| `{json.dumps(b)}` | {'(empty)' if not q else 'the user’s words'} | {r} |" for b, q, r in refusals],
        *dream_lines, "",
    ]
    EVIDENCE.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(f"{'PASS' if g else 'FAIL'} {n}: {d}" for n, g, d in checks))
    print(f"{'PASS' if ok else 'FAIL'}: wrote {EVIDENCE.relative_to(config.ROOT)}")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
