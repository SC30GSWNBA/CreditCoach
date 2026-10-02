"""Task 17: goal stated in session 1 is recalled, unprompted, in session 2; write both transcripts as evidence.

Definition of Done: a goal stated in session 1 is correctly recalled, unprompted, in session 2. This script drives the
chat UI's own functions (``creditcoach.app.main``: sign-in, each message, log-out) with live model calls, as a person
in the browser would, in a temporary memory folder so the shared ``memory/`` isn't touched. Between the sessions,
dreaming consolidates session 1 (live, ``SMALL_MODEL``), as it does at sign-in in the app.

Scenarios, from requirements.md:
    Aravind (USR-001)  Session 1: §3 #5, "Remember that I'm saving for a car and want to hit a 720 score by next
                       year." Session 2: §4 #37 "What should I work on this month?" (recall, unprompted), §4 #39 "What
                       goal did I tell you?" (read back exactly), §4 #40 "Should I aim for 800 instead?" (no silent
                       change), §4 #38 "Actually, change my target to 750..." (update, keep the rest).
    Manish (USR-013)   Session 1: §4 #35, 850 by December 2027 to buy a home. Session 2: §4 #36 "How am I doing?"

Each answer is checked automatically (keywords and the stored goal after the turn); the transcripts are in the
evidence for a person to judge.

Writes:
    docs/evidence/week-2/task-17-goal-recall.md

Run (needs OPENROUTER_API_KEY and the vector store; about 10 GPT-5 answers and 2 SMALL_MODEL dreams):
    uv run python scripts/task17_goal_recall.py
"""

import sys
import tempfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from creditcoach import config

EVIDENCE = config.ROOT / "docs" / "evidence" / "week-2" / "task-17-goal-recall.md"

SCENARIOS = [
    ("Aravind", "creditcoach_user1", "USR-001", [
        ("§3 #5", "Remember that I'm saving for a car and want to hit a 720 score by next year.",
         {"goal": (720, "2027", "car"), "says": [["720"], ["car"]]}),
    ], [
        ("§4 #37", "What should I work on this month?",
         {"goal": (720, "2027", "car"), "says": [["720"], ["car"], ["650"]]}),
        ("§4 #39", "What goal did I tell you?", {"goal": (720, "2027", "car"), "says": [["720"], ["car"], ["2027"]]}),
        ("§4 #40", "Should I aim for 800 instead?", {"goal": (720, "2027", "car"), "says": [["800"], ["720"]]}),
        ("§4 #38", "Actually, change my target to 750. I want a better rate on the car loan.",
         {"goal": (750, "2027", "car"), "says": [["750"], ["720"]]}),
    ]),
    ("Manish", "creditcoach_user13", "USR-013", [
        ("§4 #35", "Remember that I want a score of 850 by December 2027 so I can buy a home.",
         {"goal": (850, "2027-12", "home"), "says": [["850"], ["home"]]}),
    ], [
        ("§4 #36", "How am I doing?", {"goal": (850, "2027-12", "home"), "says": [["850"], ["841"], ["9 "]]}),
    ]),
]


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="creditcoach-task17-")) / "memory"
    config.MEMORY_DIR = tmp
    from creditcoach.app import main as app
    from creditcoach.evals.golden import missing_groups
    from creditcoach.memory import dream, recall, store

    app.dream.dream_in_background = lambda user_id, exclude_session=None: dream.dream(user_id, exclude_session)
    checks, body = [], []

    def goal_tuple(user_id):
        g = store.load(user_id).goal
        return (g.target_score, g.target_date, g.purpose) if g else None

    def run_session(name, username, user_id, number, turns):
        req = SimpleNamespace(username=username, session_hash=f"task17-{user_id}-{number}")
        who, _ = app.start(req)
        s = app._sessions[req.session_hash]
        context = recall.context(user_id, s.session)
        body.extend([f"### {name}, session {number} (`{s.session}`)", "",
                     "<details><summary>MEMORY the model read at the start of this session</summary>", "",
                     "```", context, "```", "", "</details>", ""])
        history = []
        for label, question, expect in turns:
            reply = app.final_reply(question, history, req)
            history += [{"role": "user", "content": question}, {"role": "assistant", "content": reply}]
            episode = store.read_episode(s.path)
            meta = next(e.meta for e in reversed(episode.events) if e.type == "assistant_message")
            text = next(e.text for e in reversed(episode.events) if e.type == "assistant_message")
            g = goal_tuple(user_id)
            want = expect["goal"]
            goal_ok = g is not None and g[0] == want[0] and g[1] == want[1] and want[2] in (g[2] or "").lower()
            missing = missing_groups(text, expect["says"])
            checks.append((f"{name} s{number} {label}: stored goal after the turn", goal_ok, f"{g}"))
            checks.append((f"{name} s{number} {label}: answer mentions {', '.join('/'.join(x) for x in expect['says'])}",
                           not missing, "missing " + str(missing) if missing else "all present"))
            tools = ", ".join(f"`{t['tool']}`" + ("" if t["ok"] else f" → {t['code']}") for t in meta.get("tools", []))
            body.extend([f"**{label} · You:** {question}", "", f"*Tools: {tools or 'none'} · stored goal after this "
                         f"turn: {g}*", "", *[f"> {l}" if l else ">" for l in text.splitlines()], ""])
        app.log_out(req)
        return s

    for name, username, user_id, first, second in SCENARIOS:
        body.extend([f"## {name} ({user_id})", ""])
        s1 = run_session(name, username, user_id, 1, first)
        d = dream.dream(user_id) or store.load(user_id).dream  # what the next sign-in would do
        checks.append((f"{name}: dreaming consolidated session 1 and kept the goal",
                       d and s1.session in d["covers"] and goal_tuple(user_id) is not None,
                       f"{len(d['semantic']['facts']) if d else 0} facts"))
        s2 = run_session(name, username, user_id, 2, second)
        recalled = next(c for c in checks if c[0].startswith(f"{name} s2") and "answer mentions" in c[0])
        checks.append((f"{name}: goal from session 1 recalled, unprompted, in session 2", recalled[1],
                       f"session 2 (`{s2.session}`) never restated the goal; first answer: {recalled[2]}"))

    ok = all(c[1] for c in checks)
    lines = ["# Task 17 Evidence: Goal Recall Across Two Sessions", "",
             f"*{date.today().isoformat()} · {config.CHAT_MODEL} (answers), {config.SMALL_MODEL} (dreaming) · Code: "
             "`creditcoach/memory/recall.py`, `creditcoach/agent/pipeline.py`, `creditcoach/app/main.py` · Tests: "
             "`tests/test_recall.py` · Script: `uv run python scripts/task17_goal_recall.py`*", "",
             "**Definition of Done:** a goal stated in session 1 is correctly recalled, unprompted, in session 2.", "",
             "**How:** the script drives the chat UI's own sign-in, message and log-out functions with live model "
             "calls, in a temporary memory folder. In session 1 the user states a goal and the model saves it with "
             "`save_goal`, in the user's own words. Session 1 is then consolidated by dreaming, as the app does at "
             "the next sign-in. Session 2 is a new session: the user never restates the goal, and the model reads "
             "it from MEMORY.", "",
             f"**Result: {'✅ PASS' if ok else '❌ FAIL'}** ({sum(c[1] for c in checks)}/{len(checks)} checks)", "",
             "| Check | Result | Detail |", "|---|---|---|",
             *[f"| {n} | {'✅' if g else '❌'} | {str(d).replace('|', '/')} |" for n, g, d in checks], "",
             "## Transcripts", "", *body]
    EVIDENCE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(f"{'PASS' if g else 'FAIL'} {n}: {d}" for n, g, d in checks))
    print(f"{'PASS' if ok else 'FAIL'}: wrote {EVIDENCE.relative_to(config.ROOT)}")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
