"""Task 9: test retrieval on "why did my credit score drop 20 points?" and compare strategies on hand-labelled queries.

Relevant chunks were labelled from chunk content before any strategy was compared. Metrics:
hit@3 (a relevant chunk in the top 3), precision@3, and MRR (1 / rank of the first relevant chunk).

    uv run python scripts/task09_retrieval_eval.py
"""

from datetime import date

from creditcoach import config
from creditcoach.rag import retrieve as R

EVIDENCE = config.ROOT / "docs" / "evidence" / "week-1" / "task-09-retrieval-test.md"
TEST_QUERY = "why did my credit score drop 20 points?"
# Why each relevant chunk helps answer the test query (used in the logged judgment).
REASONS = {
    "why-scores-drop#01": "Names the two most common short-term causes, a utilization spike (typically 10-40 points) and a hard inquiry (2-10 points), and that together they can explain a 20-point drop. This matches USR-001's recorded cause.",
    "why-scores-drop#02": "Lists the larger causes (late payment, collections, closing the oldest card), what does not lower a score, and next steps, so the answer can rule causes in or out.",
    "factor-credit-utilization#01": "Explains the 30% level, why paying in full doesn't prevent a spike (statement-date reporting), and the typical 10-40 point impact that fades one cycle after paydown.",
    "factor-credit-utilization#02": "Gives the fixes for a utilization spike: pay the highest-utilization card first, pay before the statement date.",
    "factor-hard-inquiries#00": "Explains hard inquiries (2-10 points, fading in about 12 months) and that checking your own score doesn't count.",
    "score-impact-reference#01": "The guide's impact table with typical ranges for each event.",
    "score-impact-reference#02": "How to read the table, including that two events in the same month can combine into a larger drop.",
    "factor-payment-history#00": "Explains late payments, the largest factor, which the answer should rule in or out.",
}

SCORE_DROP = {"why-scores-drop#01", "why-scores-drop#02", "factor-credit-utilization#01", "factor-credit-utilization#02",
              "factor-hard-inquiries#00", "score-impact-reference#01", "score-impact-reference#02",
              "factor-payment-history#00"}
PAYDAY = {"payday-loans-and-instant-loan-apps#00", "payday-loans-and-instant-loan-apps#01",
          "payday-loans-and-instant-loan-apps#02", "payday-loans-and-instant-loan-apps#04", "safer-alternatives#00",
          "safer-alternatives#01", "safer-alternatives#02", "minimum-due-and-interest#02"}

EVAL_SET = [
    ("why did my credit score drop 20 points?", SCORE_DROP),
    ("Why did my credit score drop 20 points this month?", SCORE_DROP),
    ("my cibil score fell suddenly, what happened?", SCORE_DROP),
    ("I applied for a new card and my balance went up, why is my score lower?", SCORE_DROP),
    ("What's my current credit utilization ratio?", {"factor-credit-utilization#00", "factor-credit-utilization#01"}),
    ("I want to buy a car in 12 months — what should I focus on?",
     {"planning-for-a-car-loan#00", "planning-for-a-car-loan#01", "planning-for-a-car-loan#02",
      "factor-hard-inquiries#01", "building-good-credit-habits#01"}),
    ("Should I take out this payday loan to pay off my credit card?", PAYDAY),
    ("is it ok to use an instant loan app to clear my card dues?", PAYDAY),
    ("Remember that I'm saving for a car and want to hit a 720 score by next year.",
     {"credit-goals-and-no-guarantees#00", "planning-for-a-car-loan#00", "planning-for-a-car-loan#01"}),
    ("Can you guarantee my score will hit 720 if I do what you said?",
     {"credit-goals-and-no-guarantees#01", "credit-repair-scams#00", "credit-repair-scams#01",
      "credit-scores-in-india#01"}),
]
STRATEGIES = {
    "A dense": dict(rerank=False, max_per_doc=None),
    "B dense + cap 2/doc": dict(rerank=False, max_per_doc=2),
    "C rerank + cap 2/doc": dict(rerank=True, fusion=False, max_per_doc=2),
    "D fusion (dense+rerank) + cap 2/doc": dict(rerank=True, fusion=True, max_per_doc=2),
}


def evaluate(options: dict) -> dict:
    hits = prec = mrr = 0.0
    rows = []
    for query, relevant in EVAL_SET:
        ids = [r.id for r in R.retrieve(query, k=3, **options)]
        first = next((i + 1 for i, cid in enumerate(ids) if cid in relevant), None)
        hits += first is not None
        prec += sum(cid in relevant for cid in ids) / 3
        mrr += 1 / first if first else 0
        rows.append((query, ids, first))
    n = len(EVAL_SET)
    return {"hit@3": hits / n, "precision@3": prec / n, "mrr": mrr / n, "rows": rows}


def main() -> None:
    results = R.retrieve(TEST_QUERY)  # production defaults: rerank + max 2 chunks per document
    judged = [(r, r.id in SCORE_DROP and r.category == "scoring_factor") for r in results]
    passed = any(ok for _, ok in judged)

    lines = ["# Task 9 Evidence: Retrieval Test\n",
             f"*{date.today().isoformat()} · Code: `creditcoach/rag/retrieve.py` · "
             "Script: `uv run python scripts/task09_retrieval_eval.py`*\n",
             "**Definition of Done:** relevant scoring-factor chunk(s) appear in the top-3 retrieved results for "
             "\"why did my credit score drop 20 points?\"\n",
             "**Retriever:** normalize the query (Indian bureau names such as CIBIL → credit score) → dense search "
             f"with `{config.EMBEDDING_MODEL}` for the 12 nearest chunks → rerank with the cross-encoder "
             f"`{config.RERANKER_MODEL}` → keep at most 2 chunks per document → top 3.\n",
             "**Relevance labels** were set from chunk content before strategies were compared. A chunk counts as "
             "relevant to this query if it explains a factor that can cause a score drop, with its typical impact "
             "or fix.\n",
             "## Logged query\n", f"```\nQuery: {TEST_QUERY}\n{R.format_results(results, preview=400)}\n```\n",
             "*Similarity is the embedding (cosine) score from the first-stage search. The final order comes from "
             "the cross-encoder reranker, which reads the query and chunk together, so ranks need not follow "
             "similarity.*\n",
             "## Judgment per retrieved chunk\n", "| Rank | Chunk | Category | Similarity | Judgment | Why |",
             "|---|---|---|---|---|---|"]
    for r, ok in judged:
        lines.append(f"| {r.rank} | `{r.id}` | {r.category} | {r.score:.3f} | {'✅ Correct' if ok else '❌ Incorrect'} | "
                     f"{REASONS.get(r.id, 'Not a scoring-factor explanation for this query.')} |")
    lines += ["", f"**Result: {'✅ PASS' if passed else '❌ FAIL'}.** "
              f"{sum(ok for _, ok in judged)} of 3 retrieved chunks are relevant scoring-factor chunks, and the top "
              f"result is {'relevant' if judged[0][1] else 'not relevant'}.\n",
              "## Strategy comparison (10 hand-labelled queries: the test query, 3 rephrasings, and sample queries 2–6)\n",
              "| Strategy | Hit@3 | Precision@3 | MRR |", "|---|---|---|---|"]
    misses = []
    for name, options in STRATEGIES.items():
        m = evaluate(options)
        lines.append(f"| {name} | {m['hit@3']:.2f} | {m['precision@3']:.2f} | {m['mrr']:.2f} |")
        print(f"{name:<38} hit@3 {m['hit@3']:.2f}  precision@3 {m['precision@3']:.2f}  MRR {m['mrr']:.2f}")
        if name.startswith("C"):
            misses = [(q, ids, f) for q, ids, f in m["rows"] if f != 1]
    lines += ["", "Hit@3: share of queries with a relevant chunk in the top 3. Precision@3: share of the top-3 chunks "
              "that are relevant. MRR: average of 1 / rank of the first relevant chunk (1.00 = always first). "
              "**Chosen: C**, the highest precision and MRR. Rank fusion (D) did not beat the reranker alone.\n",
              "Queries where the chosen strategy's first result is not relevant:\n"]
    lines += [f"- {q!r}: first relevant chunk at rank {f or 'none'} (top 3: {', '.join(ids)})" for q, ids, f in misses]
    lines += ["", "## Per-query results with the chosen strategy\n", "| Query | Top 3 |", "|---|---|"]
    for query, _ in EVAL_SET:
        lines.append(f"| {query} | {', '.join(f'`{r.id}`' for r in R.retrieve(query))} |")

    EVIDENCE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nTest query top 3: {[r.id for r in results]} -> {'PASS' if passed else 'FAIL'}")
    print(f"Wrote {EVIDENCE.relative_to(config.ROOT)}")


if __name__ == "__main__":
    main()
