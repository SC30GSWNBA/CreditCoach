# Task 9 Evidence: Retrieval Test

*2026-09-24 · Code: `creditcoach/rag/retrieve.py` · Script: `uv run python scripts/task09_retrieval_eval.py`*

**Definition of Done:** relevant scoring-factor chunk(s) appear in the top-3 retrieved results for "why did my credit score drop 20 points?"

**Retriever:** normalize the query (Indian bureau names such as CIBIL → credit score) → dense search with `sentence-transformers/all-MiniLM-L6-v2` for the 12 nearest chunks → rerank with the cross-encoder `cross-encoder/ms-marco-MiniLM-L-6-v2` → keep at most 2 chunks per document → top 3.

**Relevance labels** were set from chunk content before strategies were compared. A chunk counts as relevant to this query if it explains a factor that can cause a score drop, with its typical impact or fix.

## Logged query

```
Query: why did my credit score drop 20 points?
  1. [0.665] why-scores-drop#01  (scoring_factor)
     **Most common causes of a short-term drop** 1. **A utilization spike.** A card balance rose above roughly 30% of its limit, often after a large purchase reported before the statement date. This is one of the most common causes of a short-term dip. Typical impact: about 10 to 40 points, fading about one reporting cycle after the balance is paid down. 2. **A new hard inquiry.** You applied for a car...
  2. [0.702] why-scores-drop#02  (scoring_factor)
     **Causes of a larger or longer drop** - **A payment 30 or more days late.** Typically 60 to 110 points, with the effect fading over about two years. - **An account sent to collections.** Typically 50 to 100 points. - **Closing your oldest card.** Typically 5 to 20 points, recovering gradually.  **Things that do not lower your score** - Checking your own score (a soft inquiry). - Your salary or inc...
  3. [0.496] factor-credit-utilization#01  (scoring_factor)
     **The 30% level.** Utilization above roughly 30% on any single card, or across all cards combined, is commonly associated with score drops. This applies even if you pay your bill in full every month. Lower is generally better; many people aim to keep it under 10% to 30%.  **Why paying in full doesn't always prevent it.** Utilization is usually based on the balance your card issuer reports to the c...
```

*Similarity is the embedding (cosine) score from the first-stage search. The final order comes from the cross-encoder reranker, which reads the query and chunk together, so ranks need not follow similarity.*

## Judgment per retrieved chunk

| Rank | Chunk | Category | Similarity | Judgment | Why |
|---|---|---|---|---|---|
| 1 | `why-scores-drop#01` | scoring_factor | 0.665 | ✅ Correct | Names the two most common short-term causes, a utilization spike (typically 10-40 points) and a hard inquiry (2-10 points), and that together they can explain a 20-point drop. This matches USR-001's recorded cause. |
| 2 | `why-scores-drop#02` | scoring_factor | 0.702 | ✅ Correct | Lists the larger causes (late payment, collections, closing the oldest card), what does not lower a score, and next steps, so the answer can rule causes in or out. |
| 3 | `factor-credit-utilization#01` | scoring_factor | 0.496 | ✅ Correct | Explains the 30% level, why paying in full doesn't prevent a spike (statement-date reporting), and the typical 10-40 point impact that fades one cycle after paydown. |

**Result: ✅ PASS.** 3 of 3 retrieved chunks are relevant scoring-factor chunks, and the top result is relevant.

## Strategy comparison (10 hand-labelled queries: the test query, 3 rephrasings, and sample queries 2–6)

| Strategy | Hit@3 | Precision@3 | MRR |
|---|---|---|---|
| A dense | 1.00 | 0.70 | 0.83 |
| B dense + cap 2/doc | 1.00 | 0.67 | 0.83 |
| C rerank + cap 2/doc | 1.00 | 0.77 | 0.95 |
| D fusion (dense+rerank) + cap 2/doc | 1.00 | 0.73 | 0.85 |

Hit@3: share of queries with a relevant chunk in the top 3. Precision@3: share of the top-3 chunks that are relevant. MRR: average of 1 / rank of the first relevant chunk (1.00 = always first). **Chosen: C**, the highest precision and MRR. Rank fusion (D) did not beat the reranker alone.

Queries where the chosen strategy's first result is not relevant:

- 'my cibil score fell suddenly, what happened?': first relevant chunk at rank 2 (top 3: why-scores-drop#00, why-scores-drop#01, credit-report-and-disputes#00)

## Per-query results with the chosen strategy

| Query | Top 3 |
|---|---|
| why did my credit score drop 20 points? | `why-scores-drop#01`, `why-scores-drop#02`, `factor-credit-utilization#01` |
| Why did my credit score drop 20 points this month? | `why-scores-drop#01`, `why-scores-drop#02`, `factor-credit-utilization#01` |
| my cibil score fell suddenly, what happened? | `why-scores-drop#00`, `why-scores-drop#01`, `credit-report-and-disputes#00` |
| I applied for a new card and my balance went up, why is my score lower? | `why-scores-drop#01`, `factor-credit-utilization#01`, `why-scores-drop#02` |
| What's my current credit utilization ratio? | `factor-credit-utilization#00`, `factor-credit-utilization#01`, `score-impact-reference#01` |
| I want to buy a car in 12 months — what should I focus on? | `planning-for-a-car-loan#02`, `planning-for-a-car-loan#01`, `credit-goals-and-no-guarantees#00` |
| Should I take out this payday loan to pay off my credit card? | `payday-loans-and-instant-loan-apps#02`, `minimum-due-and-interest#02`, `payday-loans-and-instant-loan-apps#03` |
| is it ok to use an instant loan app to clear my card dues? | `minimum-due-and-interest#02`, `payday-loans-and-instant-loan-apps#02`, `safer-alternatives#00` |
| Remember that I'm saving for a car and want to hit a 720 score by next year. | `credit-goals-and-no-guarantees#00`, `planning-for-a-car-loan#00`, `credit-goals-and-no-guarantees#01` |
| Can you guarantee my score will hit 720 if I do what you said? | `credit-goals-and-no-guarantees#01`, `credit-goals-and-no-guarantees#00`, `credit-repair-scams#00` |
