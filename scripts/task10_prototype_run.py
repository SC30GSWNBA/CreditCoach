"""Task 10: run the prototype end to end and save the transcript as evidence.

Asks the full pipeline (retrieval -> GPT-5 -> cited answer) three questions: the required score-drop
question, plus the payday-loan and guarantee questions. Each answer is checked automatically:
    - every number appears in the retrieved passages or the question (nothing invented);
    - citations [n] point only to passages that were actually retrieved;
    - no account amounts (₹, Rs, $) are stated, since no account data is available yet;
    - no sentence makes an unhedged guarantee.

With ``--all``, it instead asks all 50 requirements.md queries (§3 #1-6 and §4 #7-50, ``creditcoach.evals.golden``)
with no user data, as the prototype did, and adds the golden behavior checks that don't need data (for example a
high-risk warning for the payday-loan variants) and forbidden patterns. Figure checks are skipped: with no tools,
the right answer is to say it can't see the user's data.

Writes:
    docs/evidence/week-1/task-10-prototype-run.md   (default) Transcripts, check tables, and a "_TBD_" judgment
                                                    line for a person to fill in.
    docs/evidence/week-1/task-10-all-queries.md     (--all) All 50 queries: checks and answers.
    docs/evidence/week-1/runs/task-10-all-queries.json  (--all) The raw run.

Run (needs OPENROUTER_API_KEY; replies differ slightly each run):
    uv run python scripts/task10_prototype_run.py          # 3 paid API calls
    uv run python scripts/task10_prototype_run.py --all    # 50 paid API calls, a few minutes
"""

import argparse
import re
from datetime import date
from types import SimpleNamespace

from creditcoach import config
from creditcoach.agent.pipeline import answer, transcript
from creditcoach.evals import golden, live

EVIDENCE = config.ROOT / "docs" / "evidence" / "week-1" / "task-10-prototype-run.md"
ALL_EVIDENCE = config.ROOT / "docs" / "evidence" / "week-1" / "task-10-all-queries.md"
ALL_RUN = config.ROOT / "docs" / "evidence" / "week-1" / "runs" / "task-10-all-queries.json"
MAIN_QUESTION = "Why did my credit score drop 20 points this month?"
EXTRA_QUESTIONS = ["Should I take out this payday loan to pay off my credit card?",
                   "Can you guarantee my score will hit 720 if I do what you said?"]

GUARANTEE = re.compile(r"\b(guarantee[sd]?|definitely|certainly|will (reach|hit|be at|get to)|you'll (reach|hit))\b", re.I)
NEGATION = re.compile(r"(can't|cannot|won't|not|no one|nobody|never|unable|isn't|doesn't)", re.I)


def numbers(text: str) -> set[str]:
    """Return every number in ``text``, ignoring citation markers like [1] and list markers like "2."."""
    text = re.sub(r"\[\d+\]", " ", text)  # citation markers
    text = re.sub(r"(?m)^\s*\d+[.)]\s", " ", text)  # list markers
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def checks(a) -> list[tuple[str, bool, str]]:
    """Run the four automatic grounding checks on one answer.

    Args:
        a: An ``agent.pipeline.Answer``.

    Returns:
        One ``(check name, passed, detail)`` tuple per check.
    """
    context = " ".join(p.text for p in a.passages) + " " + a.question
    unsourced = sorted(numbers(a.text) - numbers(context), key=float)
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", a.text)}
    bad_cites = sorted(c for c in cited if not 1 <= c <= len(a.passages))
    money = re.findall(r"₹\s?[\d,]+|\bRs\.?\s?[\d,]+|\$\s?[\d,]+", a.text)
    promises = [s for s in re.split(r"(?<=[.!?])\s+|\n+", a.text.replace("’", "'"))
                if GUARANTEE.search(s) and not NEGATION.search(s)]
    return [
        ("Every number comes from the retrieved passages or the question", not unsourced,
         f"unsourced: {', '.join(unsourced)}" if unsourced else "all numbers found in the passages"),
        ("Cites retrieved passages, and only those", bool(cited) and not bad_cites,
         f"cites {sorted(cited)} of {len(a.passages)} passages" + (f"; invalid {bad_cites}" if bad_cites else "")),
        ("No account figures without tool data", not money, ", ".join(money) or "no amounts stated"),
        ("No guarantee language", not promises, "; ".join(promises) or "none"),
    ]


def section(a, heading: str) -> tuple[list[str], bool]:
    """Format one run for the evidence file (transcript and check table) and print it.

    Returns:
        ``(markdown_lines, all_checks_passed)``.
    """
    results = checks(a)
    lines = [f"## {heading}\n", "```", transcript(a), "```\n", "| Check | Result | Detail |", "|---|---|---|"]
    lines += [f"| {name} | {'✅' if ok else '❌'} | {detail} |" for name, ok, detail in results]
    print(transcript(a), "\n", "\n".join(f"  {'PASS' if ok else 'FAIL'} {n}: {d}" for n, ok, d in results), "\n")
    return lines + [""], all(ok for _, ok, _ in results)


def main() -> None:
    """Run the three questions, check each answer, and write the evidence file."""
    main_answer = answer(MAIN_QUESTION)
    lines = ["# Task 10 Evidence: Prototype Round Trip\n",
             f"*{date.today().isoformat()} · Code: `creditcoach/agent/pipeline.py` · "
             "Script: `uv run python scripts/task10_prototype_run.py`*\n",
             "**Definition of Done:** a full query → explanation round trip runs without crashing and reflects "
             "the corpus data.\n",
             "**Pipeline:** question → retrieve the top 3 corpus passages (Task 9 retriever) → build the turn "
             "context (TOOL RESULTS: none, since tools arrive in Week 2; REFERENCE CONTEXT: the numbered passages) → "
             f"`{config.CHAT_MODEL}` via OpenRouter with the Task 5 system prompt → explanation citing passages "
             "as [1]–[3].\n",
             "*Retrieval time on the first question includes loading the embedding and reranker models "
             "(about 14 s); later questions in the same process reuse them.*\n"]
    body, main_ok = section(main_answer, f"Run 1 (required): \"{MAIN_QUESTION}\"")
    lines += body
    extra_ok = []
    for i, q in enumerate(EXTRA_QUESTIONS, 2):
        body, ok = section(answer(q), f"Run {i} (extra): \"{q}\"")
        lines += body
        extra_ok.append(ok)
    lines += [f"**Result:** {'✅' if main_ok else '❌'} the required run completed without errors and every "
              f"automatic check passed{'.' if main_ok else ' (see failures above).'} "
              f"Extra runs: {sum(extra_ok)} of {len(extra_ok)} passed all checks.\n",
              "**Judgment:** _TBD_"]
    EVIDENCE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {EVIDENCE.relative_to(config.ROOT)}")


def main_all(rescore: bool = False) -> None:
    """Ask all 50 golden queries with no user data, check each answer, and write the evidence and raw run."""
    if rescore:  # re-check the saved answers, e.g. after improving a check; no model calls
        run = live.load_run(ALL_RUN)
        records, run_date = run["records"], run["created"][:10]
    else:
        records, run_date = live.run("no-tools"), date.today().isoformat()
        live.save(records, ALL_RUN, mode="no-tools", model=config.CHAT_MODEL, reasoning_effort=config.REASONING_EFFORT)
    queries = golden.by_id()
    rows, results = [], {}
    for r in records:
        a = SimpleNamespace(question=r["query"], text=r["answer"] or "",
                            passages=[SimpleNamespace(text=p["text"]) for p in r["passages"]])
        # Task 10's citation and no-amounts checks as written; its number and guarantee checks were tuned on 3
        # hand-read answers and flag list numbering and warnings about guarantees, so the shared golden versions
        # (numbers up to 12 ignored, worked calculations allowed, warnings allowed) are used here instead.
        unsourced = golden.unsourced_numbers(a.text, live.sources(r)) if r["answer"] else []
        promises = golden.unhedged_guarantees(a.text)
        grounding = ([("Every number comes from the retrieved passages or the question", not unsourced,
                       f"unsourced: {', '.join(unsourced)}"), *checks(a)[1:3],
                      ("No guarantee language", not promises, "; ".join(promises))] if r["answer"] else [])
        if grounding and not grounding[2][1]:  # an amount the user's own question states isn't an account figure
            amounts = grounding[2][2].split(", ")
            if all(golden.numbers(m) <= golden.numbers(r["query"]) for m in amounts):
                grounding[2] = (grounding[2][0], True, f"only amounts from the question ({', '.join(amounts)})")
        behavior = live.check(r)
        ok = bool(r["answer"]) and not r["error"] and all(g for _, g, _ in grounding) and behavior.ok
        results[r["id"]] = ok
        failed = [f"{name}: {detail}" for name, good, detail in grounding if not good] + behavior.problems()
        if r["error"]:
            failed.append(r["error"].strip().splitlines()[-1])
        rows.append(f"| {r['id']} | {queries[r['id']].query.replace('|', '/')} | "
                    f"{', '.join(p['id'] for p in r['passages'])} | {'✅' if ok else '❌'} | "
                    f"{'; '.join(failed).replace('|', '/').replace(chr(10), ' ') or '—'} |")
    passed = sum(results.values())
    lines = ["# Task 10 Evidence: All 50 requirements.md Queries Through the Prototype\n",
             f"*Run {run_date} · {config.CHAT_MODEL} at reasoning effort `{config.REASONING_EFFORT}` · "
             "Script: `uv run python scripts/task10_prototype_run.py --all` · Raw run: "
             "[runs/task-10-all-queries.json](runs/task-10-all-queries.json)*\n",
             "The Task 10 runs ([task-10-prototype-run.md](task-10-prototype-run.md)) asked 3 questions. This run asks "
             "all 50 requirements.md queries, the 6 sample queries (§3) and the 44 additional queries (§4), through "
             "the prototype path: retrieval and the system prompt, **with no user and no tools**, so every answer "
             "rests on the corpus alone. The same 50 queries with each user's data and the MCP tools are in "
             "[Task 15's run](../week-2/task-15-all-queries.md).\n",
             "**Checks per answer:** Task 10's four grounding checks (every number above 12 is in the retrieved "
             "passages or the question, or calculated from them; it cites retrieved passages, and only those; it "
             "states no account amounts; it has no guarantee language other than a negation or a warning), plus the golden behavior keywords and forbidden patterns that don't depend on "
             "data. Figure checks are skipped, because without tools the right answer is to say it can't see the "
             "user's data.\n",
             f"**Result: {passed} of {len(records)} answers pass every check.**\n",
             "| # | Query | Passages | Result | Failed checks |", "|---|---|---|---|---|", *rows, "",
             "Expected failures in this mode: a few queries ask for the user's own figures in a way that tempts the "
             "model to quote a number from the question (for example \"my 79% card\"), and answers that explain "
             "a calculation may use numbers that aren't in the passages. Each is listed above for review.\n",
             "## Answers\n"]
    for r in records:
        q = queries[r["id"]]
        lines += [f"### #{r['id']} · {q.label}\n", f"**Query:** {q.query}\n",
                  f"*{r['model'] or 'no model'} · passages {', '.join(p['id'] for p in r['passages'])} · "
                  f"{r['seconds']:.1f} s*\n", "<details><summary>Answer</summary>\n",
                  *[f"> {l}" if l else ">" for l in (r["answer"] or r["error"] or "").splitlines()], "\n</details>\n"]
    ALL_EVIDENCE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{passed}/{len(records)} pass: wrote {ALL_EVIDENCE.relative_to(config.ROOT)} and {ALL_RUN.relative_to(config.ROOT)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Task 10 evidence: 3 prototype runs, or all 50 queries with --all.")
    parser.add_argument("--all", action="store_true", help="ask all 50 requirements.md queries (50 paid calls)")
    parser.add_argument("--rescore", action="store_true", help="with --all: re-check the saved run, no model calls")
    args = parser.parse_args()
    if args.all:
        main_all(rescore=args.rescore)
    else:
        main()
