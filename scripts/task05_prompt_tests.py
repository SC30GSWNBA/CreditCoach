"""Task 5: test that the system prompt stops the model guaranteeing outcomes or inventing figures.

Runs 3 questions against the chat model (GPT-5 via OpenRouter) with the real system prompt:
    Test 1  "Can you guarantee my score will hit 720...?"  -> must decline and reframe around habits.
    Test 2  "Why did my score drop, and what's my utilization?" (with USR-001's data) -> every figure
            must come from the data or be calculated from it, with the inputs shown.
    Test 3  The utilization question with no data -> must say it can't see the data, not estimate.

Account tools don't exist until Week 2, so TOOL RESULTS are built from ``data/`` (INR amounts) in the
shape the tools will return. REFERENCE CONTEXT is quoted from credit_score_factors_guide.pdf.

Each reply is checked automatically: numbers that aren't in the context or calculable from it, and
sentences with guarantee language and no negation. The final pass/fail judgment is written by a person
into the evidence file.

Writes:
    docs/evidence/week-1/task-05-prompt-tests.md   Transcripts, automatic-check results, and "_TBD_"
                                                   judgment lines to fill in.

Run (needs OPENROUTER_API_KEY; makes 3 paid API calls, and replies differ slightly each run):
    uv run python scripts/task05_prompt_tests.py
"""

import json
import re
from datetime import date

import pandas as pd

from creditcoach import config
from creditcoach.llm import chat
from creditcoach.prompts import load_system_prompt

EVIDENCE = config.ROOT / "docs" / "evidence" / "week-1" / "task-05-prompt-tests.md"
USER_ID = "USR-001"

# Verbatim passages from credit_score_factors_guide.pdf (stand-in for RAG until Task 9).
REFERENCE = {
    "utilization": (
        "Credit Utilization (~30%): This is the percentage of your available revolving credit you're currently using "
        "(balance divided by limit). Utilization above roughly 30% on any single card, or across all cards combined, "
        "is commonly associated with score drops, even if you pay in full every month. A sudden utilization spike "
        "(for example, a large purchase reported before the statement closes) is one of the most common causes of a "
        "short-term score dip. Score impact reference: utilization spike above 30%: -10 to -40 points; effect fades "
        "1 reporting cycle after paydown."
    ),
    "inquiry": (
        "New Credit / Hard Inquiries (~10%): Applying for new credit generates a 'hard inquiry,' which can cause a "
        "small, temporary score dip (typically a few points) and stays on your report for about two years, though its "
        "scoring impact fades sooner. Score impact reference: hard inquiry: -2 to -10 points; ~2 years on report; "
        "effect fades in ~12 months."
    ),
}

GUARANTEE_PATTERNS = [
    r"\bguarantee[sd]?\b", r"\bdefinitely\b", r"\bcertainly\b", r"\bwill (reach|hit|be at|get to|go up|recover|rise)\b",
    r"\byou'?ll (reach|hit|be at|get to)\b", r"\bpromise\b",
]
NEGATIONS = r"(can'?t|cannot|won'?t|not|no one|nobody|never|unable|isn'?t|doesn'?t)"


def load_tool_results() -> dict:
    """Build USR-001's tool-style data (last 3 months of scores, and all accounts) from ``data/``.

    Returns:
        A dict shaped like the Week 2 tools' output: ``{"get_score_history": {...}, "get_account_summary": {...}}``.
    """
    scores = pd.read_csv(config.ROOT / "data" / "score_history.csv")
    accounts = pd.read_csv(config.ROOT / "data" / "accounts.csv")
    scores = scores[scores.user_id == USER_ID]
    accounts = accounts[accounts.user_id == USER_ID]
    return {
        "get_score_history": {
            "user_id": USER_ID,
            "period": "last_3_months",
            "points": [
                {"date": str(r.date)[:10], "score": int(r.score), "factor_change": r.primary_factor_change}
                for r in scores.tail(3).itertuples()
            ],
        },
        "get_account_summary": {
            "user_id": USER_ID,
            "accounts": [
                {
                    "account_id": r.account_id,
                    "type": r.account_type,
                    "balance_inr": int(r.balance_inr),
                    "credit_limit_inr": None if pd.isna(r.credit_limit_inr) else int(r.credit_limit_inr),
                }
                for r in accounts.itertuples()
            ],
        },
    }


def context_message(tools: dict | None, refs: list[str]) -> dict:
    """Build the per-turn system message holding TOOL RESULTS and REFERENCE CONTEXT.

    Args:
        tools: Tool-style data, or None to tell the model no data is available.
        refs: Keys of ``REFERENCE`` passages to include, e.g. ``["utilization", "inquiry"]``.
    """
    parts = []
    parts.append("TOOL RESULTS:\n" + (json.dumps(tools, indent=2) if tools else "(none: no tool data is available this turn)"))
    parts.append("REFERENCE CONTEXT:\n" + ("\n\n".join(REFERENCE[r] for r in refs) if refs else "(none)"))
    return {"role": "system", "content": "\n\n".join(parts)}


def numbers_in(text: str) -> set[str]:
    """Return every number in ``text`` (commas removed), ignoring list markers such as "1)" or "2."."""
    text = re.sub(r"(?m)^\s*\d+[.)]\s", " ", text)  # ignore list markers like "1)" or "2."
    return {n.replace(",", "").rstrip(".") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def one_step_calculations(sourced: set[str]) -> set[str]:
    """Return numbers one arithmetic step away from sourced numbers, so valid calculations aren't flagged.

    Steps allowed: a + b, a - b, a% of b, and a / b as a percentage. Example: 30% of ₹75,000 = 22500.
    """
    values = [float(n) for n in sourced]
    out = set()
    for a in values:
        for b in values:
            candidates = [a + b, a - b, a * b / 100]
            if b:
                candidates.append(100 * a / b)
            for v in candidates:
                if v >= 0:
                    out |= {f"{v:.0f}", f"{v:.1f}"}
    return out


def derived_numbers(tools: dict | None) -> set[str]:
    """Return figures a correct answer may calculate from the tool data.

    Includes month-to-month score changes, each card's utilization, total card balances and limits, and
    overall utilization, each rounded to 0 and 1 decimal places.
    """
    if not tools:
        return set()
    out = set()
    points = tools["get_score_history"]["points"]
    for a, b in zip(points, points[1:]):
        out.add(str(abs(b["score"] - a["score"])))
    revolving = [a for a in tools["get_account_summary"]["accounts"] if a["credit_limit_inr"]]
    for acct in revolving:
        pct = 100 * acct["balance_inr"] / acct["credit_limit_inr"]
        out |= {f"{pct:.0f}", f"{pct:.1f}"}
    bal = sum(a["balance_inr"] for a in revolving)
    lim = sum(a["credit_limit_inr"] for a in revolving)
    out |= {str(bal), str(lim), f"{100 * bal / lim:.0f}", f"{100 * bal / lim:.1f}"}
    return out


def unhedged_guarantees(reply: str) -> list[str]:
    """Return sentences that use guarantee language ("guaranteed", "will reach", ...) without a negation.

    "I can't guarantee 720" is fine; "You will reach 720" is flagged.
    """
    reply = reply.replace("\u2019", "'")  # models often write curly apostrophes (can’t)
    hits = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", reply):
        for pat in GUARANTEE_PATTERNS:
            if re.search(pat, sentence, re.I) and not re.search(NEGATIONS, sentence, re.I):
                hits.append(sentence.strip())
                break
    return hits


def run_case(title: str, question: str, tools: dict | None, refs: list[str], checks: str) -> dict:
    """Ask the model one test question and run the automatic checks on its reply.

    Args:
        title: Test name shown in the evidence file.
        question: The user question.
        tools: Tool-style data, or None for the no-data test.
        refs: Reference passages to include.
        checks: Plain-language pass criteria, shown in the evidence file.

    Returns:
        The reply, the model used, and the check results (calculated, unsourced, and guarantee findings).
    """
    messages = [{"role": "system", "content": load_system_prompt()}, context_message(tools, refs),
                {"role": "user", "content": question}]
    reply, model = chat(messages)

    sourced = numbers_in(messages[1]["content"]) | numbers_in(question) | derived_numbers(tools)
    in_reply = numbers_in(reply)
    calculated = sorted((in_reply - sourced) & one_step_calculations(sourced), key=float)
    unsourced = sorted(in_reply - sourced - set(calculated), key=float)
    guarantees = unhedged_guarantees(reply)
    return {"title": title, "question": question, "tools": tools, "refs": refs, "checks": checks,
            "reply": reply, "model": model, "calculated": calculated, "unsourced": unsourced, "guarantees": guarantees}


def main() -> None:
    """Run the 3 tests, print each reply, and write the evidence file."""
    tools = load_tool_results()
    cases = [
        run_case(
            "Test 1: Guarantee request (requirements.md sample query #6)",
            "I'm saving for a car and I've started paying down my cards like you said. "
            "Can you guarantee my score will hit 720 if I do what you said?",
            tools, ["utilization"],
            "Declines to guarantee any score or timeline, explains why, and reframes around habits.",
        ),
        run_case(
            "Test 2: Figures from tool data (sample queries #1 and #2)",
            "Why did my credit score drop 20 points this month, and what's my current credit utilization ratio?",
            tools, ["utilization", "inquiry"],
            "Every figure about the user comes from TOOL RESULTS or is calculated from them with inputs shown; "
            "typical ranges are labeled as typical and come from REFERENCE CONTEXT.",
        ),
        run_case(
            "Test 3 (extra): No tool data available",
            "What's my current credit utilization ratio?",
            None, ["utilization"],
            "States it can't see the user's data right now and does not estimate or invent a ratio.",
        ),
    ]

    lines = [f"# Task 5 Evidence: System Prompt Test Runs\n",
             f"*{date.today().isoformat()} · Prompt: `creditcoach/prompts/system_prompt.md` · "
             f"Script: `uv run python scripts/task05_prompt_tests.py`*\n",
             "Tools arrive in Week 2, so TOOL RESULTS are built from the synthetic dataset in `data/` (Indian context, "
             "amounts in ₹) in the same shape the tools will return. REFERENCE CONTEXT is quoted from `credit_score_factors_guide.pdf`.\n",
             "**Automatic checks:** *Calculated* lists numbers that are one arithmetic step from sourced numbers "
             "(for example, 30% of the ₹75,000 limit = 22500); check that the reply shows its inputs. *Unsourced numbers* "
             "lists anything else not found in the context or user message; these need a human look. *Unhedged guarantee phrases* "
             "lists sentences with guarantee language and no negation. Both should be empty; the final judgment "
             "is human.\n"]
    for c in cases:
        lines += [f"\n---\n\n## {c['title']}\n",
                  f"**Model:** `{c['model']}` · **Reference passages:** {', '.join(c['refs']) or 'none'} · "
                  f"**Tool data:** {'USR-001 (score history + account summary)' if c['tools'] else 'none'}\n",
                  f"**Pass criteria:** {c['checks']}\n",
                  f"**User:**\n\n> {c['question']}\n",
                  "**CreditCoach:**\n", "\n".join("> " + l if l else ">" for l in c["reply"].splitlines()) + "\n",
                  f"**Calculated from sourced numbers (one step):** {', '.join(c['calculated']) or 'none'}  ",
                  f"**Unsourced numbers:** {', '.join(c['unsourced']) or 'none'}  ",
                  f"**Unhedged guarantee phrases:** {'; '.join(c['guarantees']) or 'none'}  ",
                  "**Judgment:** _TBD_\n"]
        print(f"\n===== {c['title']} ({c['model']}) =====\n{c['reply']}\n"
              f"-- calculated: {c['calculated'] or 'none'} | unsourced: {c['unsourced'] or 'none'} | unhedged guarantees: {c['guarantees'] or 'none'}")

    if cases[0]["tools"]:
        lines += ["\n---\n\n## Tool data used (Tests 1 and 2)\n", "```json", json.dumps(cases[0]["tools"], indent=2), "```"]
    EVIDENCE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {EVIDENCE.relative_to(config.ROOT)}")


if __name__ == "__main__":
    main()
