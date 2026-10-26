"""Task 24: run the 6 sample queries from requirements.md §3 end to end and fill in the expected-answers table.

Definition of Done: all 6 run and are compared against the expected-answers table.

"End to end" means through the chat UI's own functions (``creditcoach.app.main``: sign-in, each message, log-out), as
a person in the browser would, with everything built so far switched on: retrieval, both tools over MCP, memory,
the guardrail layer and the cache. Memory is a temporary folder, so the shared memory isn't touched.

Order. Query 3 expects "the stored goal (from memory)", and query 5 is the one that stores it and expects "a later
session" to use it. So Aravind (USR-001) signs in twice:

    Session 1   #5  "Remember that I'm saving for a car and want to hit a 720 score by next year."
    (dreaming consolidates session 1, as the app does at the next sign-in)
    Session 2   #1, #2, #3, #4, #6, in the table's order. The goal is never restated.

Each expected behavior is split into the separate things it asks for, and each is checked automatically from the
answer, the tool calls, the retrieved passages, the guardrail decision and the stored goal
(``creditcoach.evals.sample_rows``, shared with the Task 27 eval harness). A row passes when every one holds. The full answers are in the evidence for a person to judge.

Writes:
    docs/evidence/week-3/task-24-sample-queries.md
    docs/evidence/week-3/runs/task-24-sample-queries.json

Run (needs OPENROUTER_API_KEY and the vector store; 6 GPT-5 answers and 1 SMALL_MODEL dream):
    uv run python scripts/task24_sample_queries.py
"""

import json
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from creditcoach import cache, config
from creditcoach.evals import golden
from creditcoach.evals.sample_rows import SESSIONS, criteria, settle_later_session

WEEK3 = config.ROOT / "docs" / "evidence" / "week-3"
EVIDENCE, RUN = WEEK3 / "task-24-sample-queries.md", WEEK3 / "runs" / "task-24-sample-queries.json"
BEFORE = WEEK3 / "runs" / "task-24-sample-queries-before-fixes.json"  # the first run, kept for the comparison
USER_ID, USERNAME = "USR-001", "creditcoach_user1"


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="creditcoach-task24-")) / "memory"
    config.MEMORY_DIR = tmp
    config.MEMORY_BACKEND = "files"  # never the shared Neon database
    from creditcoach.app import main as app
    from creditcoach.memory import dream, store

    app.dream.dream_in_background = lambda user_id, exclude_session=None: dream.dream(user_id, exclude_session)
    cache.clear("answer", USER_ID)  # every answer below is written now, not replayed
    captured = []
    real_answer = app.answer

    def capturing(*args, **kwargs):
        captured.append(real_answer(*args, **kwargs))
        return captured[-1]
    app.answer = capturing

    def goal_tuple():
        g = store.load(USER_ID).goal
        return (g.target_score, g.target_date, g.purpose) if g else None

    records = {}
    for number, queries in enumerate(SESSIONS, 1):
        req = SimpleNamespace(username=USERNAME, session_hash=f"task24-{number}")
        app.start(req)
        history = []
        for qid in queries:
            q = golden.by_id()[qid]
            print(f"session {number}: #{qid} {q.query}", flush=True)
            before, t0 = goal_tuple(), time.perf_counter()
            reply = app.final_reply(q.query, history, req)
            seconds = time.perf_counter() - t0
            history += [{"role": "user", "content": q.query}, {"role": "assistant", "content": reply}]
            a = captured[-1]
            goal = goal_tuple()
            crit = criteria(qid, a, goal, before)
            records[qid] = {
                "id": qid, "session": number, "query": q.query, "expected": q.expected, "answer": a.text, "reply": reply,
                "seconds": round(seconds, 1), "model": a.model,
                "tools": [{"tool": c.tool, "arguments": c.arguments, "ok": c.ok, "code": c.code,
                           "cached": getattr(c, "cached", False)} for c in a.tool_calls],
                "passages": [{"id": p.id, "category": p.category} for p in a.passages],
                "guardrail": {"action": a.guardrail.action, "reviewed": a.guardrail.reviewed,
                              "input": [f.rule for f in a.guardrail.screen.findings],
                              "findings": [f.as_dict() for f in a.guardrail.findings]},
                "cache": a.cache["status"], "goal_before": before, "goal_after": goal,
                "criteria": [{"what": w, "held": h, "detail": d} for w, h, d in crit]}
        app.log_out(req)
        if number == 1:
            dream.dream(USER_ID)  # what the next sign-in would do
    app.answer = real_answer
    settle_later_session(records)  # #5's last clause is only known after session 2
    for r in records.values():
        r["pass"] = all(c["held"] for c in r["criteria"]) and r["model"] == config.CHAT_MODEL and r["guardrail"]["action"] != "blocked"
    run = {"created": datetime.now().isoformat(timespec="seconds"), "model": config.CHAT_MODEL, "user_id": USER_ID,
           "records": [records[i] for i in sorted(records)]}
    RUN.parent.mkdir(parents=True, exist_ok=True)
    RUN.write_text(json.dumps(run, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    sys.exit(0 if report(run) else 1)


def cell(text: str) -> str:
    return text.replace("|", "/").replace("\n", " ")


def summary(r: dict) -> str:
    """What the agent actually did, in one cell: its opening lines plus the facts of the run."""
    opening = " ".join(line.strip() for line in r["answer"].splitlines() if line.strip())
    opening = opening[:330].rsplit(" ", 1)[0] + "…" if len(opening) > 330 else opening
    tools = ", ".join(f"`{t['tool']}`" + ("" if t["ok"] else f" ({t['code']})") for t in r["tools"]) or "none"
    g = r["guardrail"]
    facts = [f"Tools: {tools}", f"passages: {', '.join(p['id'] for p in r['passages'])}",
             f"guardrail layer: {g['action']}" + (f" (input: {', '.join(g['input'])})" if g["input"] else ""),
             f"{r['seconds']} s"]
    if r["goal_after"] != r["goal_before"]:
        facts.insert(1, f"stored goal: {r['goal_after']}")
    return f"*\"{cell(opening)}\"*<br><br>{'; '.join(facts)}. [Full answer](#query-{r['id']})"


def report(run: dict) -> bool:
    recs = run["records"]
    ok = all(r["pass"] for r in recs)
    passed = sum(r["pass"] for r in recs)
    lines = ["# Task 24 Evidence: The 6 Sample Queries, End to End", "",
             f"*{run['created'][:10]} · Script: `uv run python scripts/task24_sample_queries.py` · Data: "
             f"[{RUN.name}](runs/{RUN.name})*", "",
             "**Definition of Done:** all 6 run and are compared against the expected-answers table.", "",
             f"**Result: {'✅ PASS' if ok else '❌ FAIL'}: {passed} of {len(recs)} rows pass**", "",
             f"Run live on {run['created'][:16].replace('T', ' ')} as Aravind ({run['user_id']}) through the chat UI's own "
             f"sign-in, message and log-out functions, with `{run['model']}`, both tools over MCP, memory, the guardrail "
             "layer and the cache all on. Query 5 stores the goal that query 3 expects to find in memory, so it ran "
             "first, in its own session; the other five ran in a second session, in the table's order, without the "
             "goal being restated.", "",
             "## Expected-answers table, filled in", "",
             "| # | Input / Query | Expected Agent Behavior (requirements.md §3) | Actual output | Checked against the expectation | Result |",
             "|---|---|---|---|---|---|"]
    for r in recs:
        checks = "<br>".join(f"{'✅' if c['held'] else '❌'} {cell(c['what'])}" for c in r["criteria"])
        lines.append(f"| {r['id']} | \"{r['query']}\" | {cell(r['expected'])} | {summary(r)} | {checks} | "
                     f"{'✅ Pass' if r['pass'] else '❌ Fail'} |")
    lines += ["", "A row passes when every check in it holds, the answer came from the main model and the guardrail layer "
              "did not have to block it. The checks are automatic (keywords, tool calls, passages, the stored goal, "
              "figure tracing); the full answers follow for a person to judge.", "",
              "## Checks in detail", ""]
    for r in recs:
        lines += [f"**Query {r['id']}** (session {r['session']})", "", "| Expected | Held | Evidence |", "|---|---|---|",
                  *(f"| {cell(c['what'])} | {'✅' if c['held'] else '❌'} | {cell(c['detail'])} |" for c in r["criteria"]), ""]
    if BEFORE.exists():
        was = {r["id"]: r for r in json.loads(BEFORE.read_text(encoding="utf-8"))["records"]}
        now = {r["id"]: r for r in recs}
        softened = next((f["matched"][0] for f in was[4]["guardrail"]["findings"]), "")
        lines += ["## Bugs found and fixed", "",
                  f"The first run ([{BEFORE.name}](runs/{BEFORE.name})) passed {sum(r['pass'] for r in was.values())} of 6. "
                  "It found two things:", "",
                  "| Query | What the first run showed | Cause | Fix | Now |", "|---|---|---|---|---|",
                  f"| 4 | The user saw a correct refusal, but only because the guardrail layer rewrote the first draft "
                  f"({was[4]['seconds']} s). The draft declined the loan and then added \"{softened}…\" with steps for "
                  "taking one anyway. The same draft appeared in the Task 21 runs. | The system prompt told the model "
                  "not to endorse a predatory product, but not that advice for going ahead anyway undoes the refusal. | "
                  "System prompt, hard rule 3: keep the refusal firm; the regulator's safeguards may be stated as "
                  "facts, not as a checklist for taking the loan. Checked on 8 more live product questions (#4, #29, "
                  "#32): none needed a rewrite, and #32 still names the RBI safeguards. | Guardrail layer: "
                  f"{now[4]['guardrail']['action']}, {now[4]['seconds']} s |",
                  "| 6 | Marked as failing \"explains that scores depend on factors outside the plan\". | The check, not "
                  "the answer: the answer said scoring models aren't public, lenders report on their own timelines and the "
                  "same action moves two people's scores differently. The check looked only for words such as "
                  "\"outside\" and \"depend\". | The check now accepts those explanations. No change to the agent. | "
                  f"{'✅ Pass' if now[6]['pass'] else '❌ Fail'} |", ""]
    lines += ["## Full answers", ""]
    for r in recs:
        g = r["guardrail"]
        lines += [f"### Query {r['id']}", "", f"Session {r['session']} · **You:** {r['query']}", "",
                  f"*Tools: {', '.join(t['tool'] + (' (cached)' if t['cached'] else '') for t in r['tools']) or 'none'} · "
                  f"guardrail layer: {g['action']}"
                  + (f", after rewriting a draft that broke {', '.join(sorted({f['rule'] for f in g['findings']}))}" if g["findings"] else "")
                  + f" · answer cache: {r['cache']} · stored goal after this turn: {r['goal_after']} · {r['seconds']} s*", "",
                  *[f"> {line}" if line else ">" for line in r["reply"].splitlines()], ""]
    EVIDENCE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for r in recs:
        failed = [c["what"] + " (" + c["detail"] + ")" for c in r["criteria"] if not c["held"]]
        print(f"{'PASS' if r['pass'] else 'FAIL'} #{r['id']} {r['seconds']}s guardrail={r['guardrail']['action']} "
              f"cache={r['cache']}" + (": " + "; ".join(failed) if failed else ""))
    print(f"{'PASS' if ok else 'FAIL'}: {passed}/{len(recs)}; wrote {EVIDENCE.relative_to(config.ROOT)}")
    return ok


if __name__ == "__main__":
    if "--report" in sys.argv:
        sys.exit(0 if report(json.loads(RUN.read_text(encoding="utf-8"))) else 1)
    main()
