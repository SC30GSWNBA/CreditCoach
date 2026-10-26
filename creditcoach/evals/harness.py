"""The eval harness (Task 27): the expected-answers table as automated test cases, each with scorers, in one command.

    uv run python -m creditcoach.evals                  # the 6 rows of requirements.md §3
    uv run python -m creditcoach.evals --all            # and the 44 §4 queries: all 50
    uv run python -m creditcoach.evals --label baseline # name the run (Task 28's baseline, Task 30's re-run)
    uv run python -m creditcoach.evals --rescore        # score the saved run again: no answers, no judge calls

Cases
    §3 #1-6   Run as Task 24 did, through the chat UI's own sign-in, message and log-out functions, signed in as
              Aravind (USR-001): #5 alone in session 1 (it stores the goal), then #1, #2, #3, #4, #6 in session 2,
              where #3 must use that goal without being told it.
    §4 #7-50  With ``--all``: each as one turn signed in as its user (``live.run``; #45 with the account tool forced
              to time out). Twelve depend on a stored goal or an earlier turn that this run doesn't set up (the
              golden ``needs``); they are scored as asked and flagged, so a failure there is read with that in mind.

Scorers (each gives a ``Score``: name, passed, value from 0 to 1, detail)
    expected  §3: every separate thing the row's expected behavior asks for (``sample_rows.criteria``), including
              that every figure traces to the tool output or the library. §4: the golden checks (tools called,
              figures and behavior keywords, forbidden patterns, no unhedged guarantee).
    figures   §4 only (§3 has it inside ``expected``): no figure in the answer that can't be traced to the tool
              output, the passages or the question.
    judge     An independent ``SMALL_MODEL`` reads the question, the expected behavior from requirements.md, the
              data the agent had and the reply, and answers: does it do what is expected; is it grounded (1-5);
              is it clear and kind for a first-time borrower (1-5). Passes on meets-expected, grounded >= 4 and
              clear >= 3; its value is (grounded + clear) / 10.
    run       It answered without crashing, with the main model (not the fallback), and the guardrail layer didn't
              have to block it.
A case passes when every scorer passes. The run's score is the share of cases that pass. Each case's time is
recorded too (a latency category for the Task 29 error analysis), but doesn't decide a pass.

Tester verdicts: every case keeps a ``human`` list, empty until real users' verdicts on that answer are added
(Task 29). The report shows them beside the automatic result; they never change the automatic score.

Langfuse: every case is one trace (``eval.case`` with the whole answer under it), tagged ``eval`` and
``eval:<label>``, and its scores are attached to it (``eval.pass``, ``eval.expected``, ``eval.judge.grounded``,
``eval.judge.clear``), so a failing case opens straight onto its trace. Without Langfuse keys the traces stay in
``.traces/`` and the scores in the run file.

Answers are never cached (the cache is off for the whole run, so every answer and tool call is fresh) and memory
goes to a temporary folder, so no user's real memory is read or written.

Writes:
    docs/evidence/week-4/eval-<label>.md          the report: score, per-case pass/fail and why, the answers
    docs/evidence/week-4/runs/eval-<label>.json   the run, which ``--rescore`` and later comparisons read

Cost: 6 GPT-5 answers, 1 ``SMALL_MODEL`` dream and 6 judge calls; with ``--all``, about 100-150 more GPT-5 calls
(tool rounds) and 44 more judge calls.
"""

import json
import re
import statistics
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from creditcoach import cache, config, llm
from creditcoach import observability as obs
from creditcoach.evals import golden, live, sample_rows
from creditcoach.guardrails import checks as rails

WEEK4 = config.ROOT / "docs" / "evidence" / "week-4"
USER_ID, USERNAME = "USR-001", "creditcoach_user1"  # Aravind, as in Task 24
SOURCES_FOR_JUDGE = 12000  # characters of the agent's data the judge reads

JUDGE_PROMPT = """You grade one reply from CreditCoach, a credit coach for first-time borrowers in India. You get the \
user's message, what the reply is expected to do (from the product requirements), the data CreditCoach had for this \
turn (its tool results and library passages, possibly cut short) and the reply.

Return only JSON: {"meets_expected": true or false, "grounded": 1-5, "clear": 1-5, "why": "<one or two sentences>"}

meets_expected: the reply does everything the expected behavior asks for and nothing it rules out. The wording need \
not match. If the expected behavior needs something the data doesn't show (an earlier session, a stored goal), \
judge whether the reply handles that sensibly.
grounded: 5 = every figure and claim about the user's own credit comes from the data, and general credit facts \
agree with the library; 3 = a small unsupported detail; 1 = it invents or contradicts the user's figures.
clear: 5 = plain, warm and specific: next steps a 22-year-old first-time borrower could act on today; 3 = correct \
but long, generic or heavy on jargon; 1 = confusing, preachy or alarming."""


@dataclass
class Score:
    """One scorer's verdict on one case."""
    name: str
    passed: bool
    value: float
    detail: str


# ---- Running the cases ----

def case_span(q: golden.Query, label: str):
    """The span one case runs in: a new trace, tagged so the run can be found in Langfuse."""
    return obs.span("eval.case", root=True, carry={"langfuse.trace.tags": ["eval", f"eval:{label}"]},
                    **{"langfuse.trace.name": f"eval {q.label}", "eval.case": q.id, "eval.run": label,
                       "eval.expected_behavior": q.expected})


def run_sample_rows(label: str) -> list[dict]:
    """Run the 6 sample queries through the chat UI's functions, in Task 24's two sessions; one record each."""
    config.MEMORY_DIR = Path(tempfile.mkdtemp(prefix="creditcoach-eval-")) / "memory"
    config.MEMORY_BACKEND = "files"  # never the shared Neon database
    from creditcoach.app import main as app  # here, so the memory settings above are in force
    from creditcoach.memory import dream, store

    in_background, real_answer = app.dream.dream_in_background, app.answer
    app.dream.dream_in_background = lambda user_id, exclude_session=None: dream.dream(user_id, exclude_session)
    captured = []

    def capturing(*args, **kwargs):
        captured.append(real_answer(*args, **kwargs))
        return captured[-1]

    def goal():
        g = store.load(USER_ID).goal
        return [g.target_score, g.target_date, g.purpose] if g else None

    app.answer, records = capturing, []
    try:
        for number, ids in enumerate(sample_rows.SESSIONS, 1):
            req = SimpleNamespace(username=USERNAME, session_hash=f"eval-{label}-{number}")
            app.start(req)
            history = []
            for qid in ids:
                q = golden.by_id()[qid]
                print(f"  §3 #{qid} (session {number}) {q.query}", flush=True)
                before, error, reply, a, t0 = goal(), None, "", None, time.perf_counter()
                captured.clear()
                with case_span(q, label):
                    try:
                        reply = app.final_reply(q.query, history, req)
                        a = captured[-1] if captured else None
                    except Exception as exc:  # recorded, so one crash doesn't lose the run
                        error = f"{type(exc).__name__}: {exc}"
                    trace_id = obs.trace_id()
                if a is None and error is None:
                    error = f"no answer: the chat replied {reply[:200]!r}"
                history += [{"role": "user", "content": q.query}, {"role": "assistant", "content": reply}]
                records.append({**_base(q), "session": number, "seconds": round(time.perf_counter() - t0, 1),
                                "error": error, "trace_id": trace_id, "reply": reply,
                                "answer": a.text if a else "", "model": a.model if a else None,
                                "guardrail": a.guardrail.action if a else None,
                                "tools": [{"tool": c.tool, "ok": c.ok, "code": c.code} for c in a.tool_calls] if a else [],
                                "passages": [p.id for p in a.passages] if a else [],
                                "snapshot": sample_rows.snapshot(a) if a else None,
                                "goal_before": before, "goal_after": goal()})
            app.log_out(req)
            if number == 1:
                dream.dream(USER_ID)  # what the next sign-in does
    finally:
        app.answer, app.dream.dream_in_background = real_answer, in_background
    return records


def run_additional(label: str) -> list[dict]:
    """Run the 44 §4 queries live, each as one turn signed in as its user; one record each."""
    ids = [q.id for q in golden.load() if q.section != "3"]
    print(f"  §4: {len(ids)} queries, 4 at a time", flush=True)
    recs = live.run("tools", ids=ids, case_span=lambda q: case_span(q, label))
    by_id = golden.by_id()
    return [{**r, **_base(by_id[r["id"]]),
             "tools": [{"tool": c["tool"], "ok": c["ok"], "code": c["code"]} for c in r["tool_calls"]],
             "passages_full": r["passages"], "passages": [p["id"] for p in r["passages"]],
             "answer": r["answer"] or ""} for r in recs]


def _base(q: golden.Query) -> dict:
    return {"id": q.id, "section": q.section, "label": q.label, "user_id": q.user_id, "query": q.query,
            "expected": q.expected, "needs": q.needs, "fault": q.fault, "human": []}


# ---- Scoring ----

def sources(rec: dict) -> str:
    """The data the agent had for this answer: what its figures may come from and what the judge reads."""
    if rec["section"] == "3":
        return rec["snapshot"]["sources"] if rec["snapshot"] else ""
    return live.sources({**rec, "passages": rec["passages_full"]})


def judge(rec: dict) -> dict:
    """The independent small-model verdict on one answer (see ``JUDGE_PROMPT``); ``{"error": ...}`` if it failed."""
    if not rec["answer"]:
        return {"error": "no answer to judge"}
    data = sources(rec)
    if len(data) > SOURCES_FOR_JUDGE:
        data = data[:SOURCES_FOR_JUDGE] + "\n[... cut short]"
    prompt = (f"USER MESSAGE:\n{rec['query']}\n\nEXPECTED BEHAVIOR:\n{rec['expected']}\n\n"
              f"DATA CREDITCOACH HAD:\n{data}\n\nREPLY:\n{rec['answer']}")
    try:
        with obs.span("eval.judge", root=True, carry={"langfuse.trace.tags": ["eval", "eval-judge"]},
                      **{"eval.case": rec["id"], "eval.trace": rec["trace_id"]}):
            reply, model = llm.chat([{"role": "system", "content": JUDGE_PROMPT}, {"role": "user", "content": prompt}],
                                    model=config.SMALL_MODEL, effort="low")
        verdict = json.loads(reply[reply.index("{"):reply.rindex("}") + 1])
        return {"meets_expected": bool(verdict["meets_expected"]), "grounded": int(verdict["grounded"]),
                "clear": int(verdict["clear"]), "why": str(verdict.get("why", "")), "model": model}
    except Exception as exc:  # a judge failure fails that scorer, not the run
        return {"error": f"{type(exc).__name__}: {exc}"}


def judge_score(j: dict) -> Score:
    if "error" in j:
        return Score("judge", False, 0.0, f"judge failed: {j['error']}")
    ok = j["meets_expected"] and j["grounded"] >= 4 and j["clear"] >= 3
    return Score("judge", ok, (j["grounded"] + j["clear"]) / 10,
                 f"meets expected: {'yes' if j['meets_expected'] else 'no'}; grounded {j['grounded']}/5; "
                 f"clear {j['clear']}/5. {j['why']}")


def run_score(rec: dict, model: str) -> Score:
    problems = []
    if rec["error"]:
        problems.append(f"crashed: {rec['error'].strip().splitlines()[-1]}")
    elif not rec["answer"]:
        problems.append("no answer")
    else:
        if rec["model"] != model:
            problems.append(f"answered by {rec['model']}, not {model}")
        if rec["guardrail"] == "blocked":
            problems.append("the guardrail layer blocked the answer")
    return Score("run", not problems, 0.0 if problems else 1.0,
                 "; ".join(problems) or f"answered by {rec['model']}; guardrail layer: {rec['guardrail']}")


def score_run(run: dict) -> None:
    """Score every case in a run, in place: ``criteria`` (§3), ``scores``, ``pass``. Reads a saved judge verdict."""
    recs = run["records"]
    sample = {r["id"]: r for r in recs if r["section"] == "3"}
    for r in sample.values():
        if r["snapshot"] is None:
            r["criteria"] = []
            continue
        crit = sample_rows.criteria(r["id"], sample_rows.restore(r["snapshot"]), r["goal_after"], r["goal_before"])
        r["criteria"] = [{"what": w, "held": h, "detail": d} for w, h, d in crit]
    sample_rows.settle_later_session(sample)
    for r in recs:
        scores = []
        if r["section"] == "3":
            crit = r["criteria"]
            held = sum(bool(c["held"]) for c in crit)
            missed = [f"{c['what']} ({c['detail']})" for c in crit if not c["held"]]
            scores.append(Score("expected", bool(crit) and not missed, held / len(crit) if crit else 0.0,
                                "; ".join(missed) or f"all {len(crit)} expectations held"))
        else:
            chk = live.check({**r, "mode": "tools"})
            problems = chk.problems()
            scores.append(Score("expected", chk.ok and not r["error"], 0.0 if problems or r["error"] else 1.0,
                                "; ".join(problems) or "tools, figures and behavior all as expected"))
            stray = golden.untraced_numbers(r["answer"], sources(r), known=rails.COMMON) if r["answer"] else []
            scores.append(Score("figures", bool(r["answer"]) and not stray, 0.0 if stray else 1.0,
                                f"untraced: {', '.join(stray)}" if stray else "every figure traced"))
        scores += [judge_score(r.get("judge") or {"error": "not judged"}), run_score(r, run["model"])]
        r["scores"] = [asdict(s) for s in scores]
        r["pass"] = all(s.passed for s in scores)


def push_scores(recs: list[dict]) -> int:
    """Attach each case's scores to its Langfuse trace. Returns how many cases were sent (0 without keys)."""
    sent = 0
    for r in recs:
        if not r["trace_id"]:
            continue
        by = {s["name"]: s for s in r["scores"]}
        failed = "; ".join(f"{s['name']}: {s['detail']}" for s in r["scores"] if not s["passed"])
        ok = obs.score(r["trace_id"], "eval.pass", r["pass"], failed or "every scorer passed")
        if ok:
            obs.score(r["trace_id"], "eval.expected", by["expected"]["value"], by["expected"]["detail"])
            j = r.get("judge") or {}
            if "error" not in j:
                obs.score(r["trace_id"], "eval.judge.grounded", j["grounded"], j["why"])
                obs.score(r["trace_id"], "eval.judge.clear", j["clear"], j["why"])
            sent += 1
    return sent


# ---- The whole run ----

def paths(label: str) -> tuple[Path, Path]:
    """The report and run file for a label."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", label):
        raise ValueError(f"label {label!r}: use lowercase letters, digits and hyphens")
    return WEEK4 / f"eval-{label}.md", WEEK4 / "runs" / f"eval-{label}.json"


def run(label: str = "latest", everything: bool = False) -> dict:
    """Answer, judge and score every case, send the scores to Langfuse, and save the run and its report."""
    report_path, run_path = paths(label)
    started = time.perf_counter()
    with cache.disabled():  # every answer and tool call fresh: the eval measures the agent, not the cache
        print("Running the 6 sample queries (requirements.md §3)", flush=True)
        recs = run_sample_rows(label)
        if everything:
            print("Running the additional queries (requirements.md §4)", flush=True)
            recs += run_additional(label)
    print(f"Judging {len(recs)} answers with {config.SMALL_MODEL}", flush=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        for r, j in zip(recs, pool.map(judge, recs)):
            r["judge"] = j
    result = {"created": datetime.now().isoformat(timespec="seconds"), "label": label,
              "scope": "all" if everything else "sample", "model": config.CHAT_MODEL, "judge_model": config.SMALL_MODEL,
              "minutes": round((time.perf_counter() - started) / 60, 1), "records": sorted(recs, key=lambda r: r["id"])}
    score_run(result)
    result["langfuse_cases"] = push_scores(result["records"])
    obs.flush()
    save(result, run_path)
    write_report(result, report_path, run_path)
    return result


def save(result: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def rescore(label: str = "latest") -> dict:
    """Score a saved run again with the current scorers (no answers, no judge calls) and rewrite its report."""
    report_path, run_path = paths(label)
    result = json.loads(run_path.read_text(encoding="utf-8"))
    score_run(result)
    save(result, run_path)
    write_report(result, report_path, run_path)
    return result


def summary(result: dict) -> dict:
    """The run's headline numbers."""
    recs = result["records"]
    part = lambda rs: {"cases": len(rs), "passed": sum(r["pass"] for r in rs),  # noqa: E731
                       "score": round(sum(r["pass"] for r in rs) / len(rs), 3) if rs else None}
    judged = [r["judge"] for r in recs if "error" not in (r.get("judge") or {"error": 1})]
    secs = [r["seconds"] for r in recs]
    return {"all": part(recs), "sample": part([r for r in recs if r["section"] == "3"]),
            "additional": part([r for r in recs if r["section"] != "3"]),
            "flagged": part([r for r in recs if unset(r)]),
            "by_scorer": {name: sum(s["passed"] for r in recs for s in r["scores"] if s["name"] == name)
                          for name in ("expected", "figures", "judge", "run")},
            "judge_grounded": round(statistics.mean(j["grounded"] for j in judged), 2) if judged else None,
            "judge_clear": round(statistics.mean(j["clear"] for j in judged), 2) if judged else None,
            "median_seconds": round(statistics.median(secs), 1) if secs else None,
            "max_seconds": max(secs) if secs else None}


# ---- Report ----

def unset(rec: dict) -> bool:
    """True if the case depends on a stored goal or an earlier turn this run doesn't set up (§4 only: the §3
    sessions set up what #3 and #5 need)."""
    return rec["section"] != "3" and bool(rec["needs"])


def cell(text: str) -> str:
    return str(text).replace("|", "/").replace("\n", " ")


def write_report(result: dict, path: Path, run_path: Path) -> None:
    s, recs = summary(result), result["records"]
    a = s["all"]
    lines = [f"# Eval Run: {result['label']}", "",
             f"*{result['created'].replace('T', ' ')[:16]} · `uv run python -m creditcoach.evals"
             f"{' --all' if result['scope'] == 'all' else ''} --label {result['label']}` · "
             f"Data: [{run_path.name}](runs/{run_path.name})*", "",
             f"**Score: {a['passed']} of {a['cases']} cases pass ({a['score']:.0%})**", "",
             "| | Cases | Pass | Score |", "|---|---|---|---|",
             f"| Sample queries (requirements.md §3) | {s['sample']['cases']} | {s['sample']['passed']} | {s['sample']['score']:.0%} |"]
    if s["additional"]["cases"]:
        lines += [f"| Additional queries (§4) | {s['additional']['cases']} | {s['additional']['passed']} | {s['additional']['score']:.0%} |",
                  f"| of which depend on setup this run doesn't do (golden `needs`) | {s['flagged']['cases']} | "
                  f"{s['flagged']['passed']} | {s['flagged']['score']:.0%} |"]
    lines += ["",
              f"Answers by `{result['model']}`, judged by `{result['judge_model']}`; cache off; memory in a temporary "
              f"folder. Judge averages: grounded {s['judge_grounded']}/5, clear {s['judge_clear']}/5. Time per answer: "
              f"median {s['median_seconds']} s, longest {s['max_seconds']} s. Run took {result['minutes']} min. "
              f"Scores sent to Langfuse for {result.get('langfuse_cases', 0)} of {a['cases']} cases (tag `eval:{result['label']}`).",
              "", "Cases passing each scorer: " + ", ".join(f"{k} {v}" for k, v in s["by_scorer"].items() if
                                                             k != "figures" or s["additional"]["cases"]) + ".", "",
              "## Cases", "",
              "| Case | Query | Expected (requirements.md) | Expected checks | Figures | Judge | Run | Result | Time |",
              "|---|---|---|---|---|---|---|---|---|"]
    for r in recs:
        by = {x["name"]: x for x in r["scores"]}
        mark = lambda name: ("✅" if by[name]["passed"] else "❌") if name in by else "–"  # noqa: E731
        figures = mark("figures") if r["section"] != "3" else "in checks"
        flag = " ⚑" if unset(r) else ""
        lines.append(f"| [{r['label']}](#case-{r['id']}){flag} | \"{cell(r['query'])}\" | {cell(r['expected'])} | "
                     f"{mark('expected')} {by['expected']['value']:.0%} | {figures} | {mark('judge')} "
                     f"{by['judge']['value']:.0%} | {mark('run')} | {'✅ Pass' if r['pass'] else '❌ Fail'} | {r['seconds']} s |")
    lines += ["", "⚑ depends on a stored goal or an earlier turn that this run doesn't set up (see the case).", ""
              ] if any(unset(r) for r in recs) else [""]
    lines += ["A case passes when every scorer passes: **expected** (each thing requirements.md expects, checked "
              "automatically), **figures** (every figure traced to the data), **judge** (an independent small model: "
              "meets the expected behavior, grounded ≥ 4/5, clear ≥ 3/5) and **run** (no crash, main model, not "
              "blocked). See `creditcoach/evals/harness.py`.", "",
              "## Tester verdicts", ""]
    verdicts = [(r, h) for r in recs for h in r["human"]]
    lines += (["| Case | Tester | Verdict | Feedback |", "|---|---|---|---|",
               *(f"| {r['label']} | {cell(h.get('tester', ''))} | {cell(h.get('verdict', ''))} | {cell(h.get('feedback', ''))} |"
                 for r, h in verdicts)] if verdicts else
              ["None recorded for this run yet. Verdicts from real users on these answers go in each case's `human` list "
               "in the run file and are shown here; they don't change the automatic score."])
    lines += ["", "## Case details", ""]
    for r in recs:
        lines += [f"### Case {r['id']}", "",
                  f"**{r['label']}**" + (f" · session {r['session']}" if r.get("session") else "") +
                  f" · {r['user_id']} · {'✅ Pass' if r['pass'] else '❌ Fail'} · {r['seconds']} s" +
                  (f" · trace `{r['trace_id']}`" if r["trace_id"] else ""), "",
                  f"**You:** {r['query']}", "", f"**Expected:** {r['expected']}", ""]
        if unset(r):
            lines += [f"⚑ Needs: {'; '.join(r['needs'])}." + (f" Fault injected: {r['fault']}." if r["fault"] else ""), ""]
        lines += ["| Scorer | Result | Detail |", "|---|---|---|",
                  *(f"| {x['name']} | {'✅' if x['passed'] else '❌'} {x['value']:.0%} | {cell(x['detail'])} |"
                    for x in r["scores"]), ""]
        if r.get("criteria"):
            lines += ["| Expected | Held | Evidence |", "|---|---|---|",
                      *(f"| {cell(c['what'])} | {'✅' if c['held'] else '❌'} | {cell(c['detail'])} |" for c in r["criteria"]), ""]
        tools = ", ".join(t["tool"] + ("" if t["ok"] else f" ({t['code']})") for t in r["tools"]) or "none"
        lines += [f"*Tools: {tools} · passages: {', '.join(r['passages']) or 'none'} · guardrail layer: {r['guardrail']}*", "",
                  "<details><summary>Answer</summary>", "",
                  *([f"> {line}" if line else ">" for line in r["answer"].splitlines()] or ["*(no answer)*"]),
                  "", "</details>", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
