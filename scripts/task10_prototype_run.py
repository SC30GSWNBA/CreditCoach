"""Task 10: run the prototype end to end and save the transcript as evidence.

Asks the full pipeline (retrieval -> GPT-5 -> cited answer) three questions: the required score-drop
question, plus the payday-loan and guarantee questions. Each answer is checked automatically:
    - every number appears in the retrieved passages or the question (nothing invented);
    - citations [n] point only to passages that were actually retrieved;
    - no account amounts (₹, Rs, $) are stated, since no account data is available yet;
    - no sentence makes an unhedged guarantee.

Writes:
    docs/evidence/week-1/task-10-prototype-run.md   Transcripts, check tables, and a "_TBD_" judgment
                                                    line for a person to fill in.

Run (needs OPENROUTER_API_KEY; makes 3 paid API calls, and replies differ slightly each run):
    uv run python scripts/task10_prototype_run.py
"""

import re
from datetime import date

from creditcoach import config
from creditcoach.agent.pipeline import answer, transcript

EVIDENCE = config.ROOT / "docs" / "evidence" / "week-1" / "task-10-prototype-run.md"
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


if __name__ == "__main__":
    main()
