# CreditCoach RAG Corpus

The documents CreditCoach retrieves from to explain credit scores. There are 17 short Markdown documents in three categories:

- **`scoring_factor`**: how scores work and what moves them
- **`financial_literacy`**: habits, goals, credit reports
- **`product_risk`**: payday loans and instant loan apps, credit-repair scams, safer alternatives

Content drawn from `credit_score_factors_guide.pdf` is attributed to it in each document's `source` field. India-specific content (credit bureaus, the 300–900 range, DPD, RBI digital-lending safeguards, complaint routes) is general education written by the CreditCoach team. It avoids exact figures we couldn't source.

## Document format

Each file starts with front matter that the ingestion pipeline (Task #8) stores as chunk metadata:

```
---
id: factor-credit-utilization      # unique, stable
title: Credit utilization
category: scoring_factor           # scoring_factor | financial_literacy | product_risk
source: credit_score_factors_guide.pdf §2 and §7
queries: [1, 2, 3]                 # requirements.md sample queries this document helps answer
---
```

Keep each document to one topic of about 150–500 words, written in plain language. Label every impact range as typical, never as a prediction.

## Check the corpus

```bash
uv run python scripts/task07_corpus_report.py
```

This validates the front matter and confirms that all 6 sample queries and every section of the factors guide are covered. It writes the result to `docs/evidence/week-1/task-07-corpus-summary.md`.
