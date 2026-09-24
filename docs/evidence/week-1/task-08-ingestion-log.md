# Task 8 Evidence: Ingestion Pipeline Log

*2026-09-24 · Command: `uv run python -m creditcoach.rag.ingest` · Code: `creditcoach/rag/ingest.py`*

**Pipeline:** load 17 Markdown documents from `corpus/` → split into semantic blocks (paragraphs, whole lists, whole tables) → pack into chunks of at most 240 tokens, each prefixed with its document title → embed locally with `all-MiniLM-L6-v2` (384 dimensions, normalized, cosine) → store in a persistent ChromaDB collection with metadata (document id, title, category, source, sample-query tags). Each run rebuilds the collection, so re-running never duplicates chunks.

**Checks built into the run:** the store's chunk count must equal the number of chunks and embeddings produced, and no chunk may exceed the embedding model's 256-token input limit (anything longer would be silently truncated and its end never embedded).

## Console log

```
[ingest] Loaded 17 documents from corpus/
[ingest] Chunked into 45 chunks (max 240 tokens each; model limit 256) - words min 25 / max 185 / avg 113, tokens max 233
[ingest] Embedded 45 chunks with sentence-transformers/all-MiniLM-L6-v2 (dimension 384)
[ingest] Stored 45 chunks in ChromaDB collection 'creditcoach_corpus' at .chroma/
[ingest]   scoring_factor     18 chunks
[ingest]   financial_literacy 16 chunks
[ingest]   product_risk       11 chunks
[ingest]   credit-scores-in-india             2 chunks
[ingest]   factor-payment-history             2 chunks
[ingest]   factor-credit-utilization          3 chunks
[ingest]   factor-credit-history-length       2 chunks
[ingest]   factor-hard-inquiries              2 chunks
[ingest]   factor-credit-mix                  1 chunk
[ingest]   score-impact-reference             3 chunks
[ingest]   why-scores-drop                    3 chunks
[ingest]   no-credit-history                  2 chunks
[ingest]   building-good-credit-habits        3 chunks
[ingest]   minimum-due-and-interest           3 chunks
[ingest]   planning-for-a-car-loan            3 chunks
[ingest]   credit-goals-and-no-guarantees     2 chunks
[ingest]   credit-report-and-disputes         3 chunks
[ingest]   payday-loans-and-instant-loan-apps 5 chunks
[ingest]   credit-repair-scams                2 chunks
[ingest]   safer-alternatives                 4 chunks
[ingest] Check: expected 45 chunks, store has 45; chunks truncated by the model: 0 -> OK
[ingest] Done in 5.2s
```

## Result

The pipeline ran with no errors. **Expected chunk count: 45. Chunks in the vector store: 45. Chunks truncated by the model: 0.**

## Issues found and fixed while building

| Issue | Fix |
|---|---|
| First version, sized by words, left 6 of 39 chunks over the model's 256-token limit (largest 344 tokens), so their endings were never embedded, including "free credit counselling" in the safer-alternatives list | Chunk size is now measured in model tokens (≤ 240 including the title); oversized blocks split at list-item boundaries |
| Short intros and closing caveats became tiny chunks without context | Chunks under 40 words merge into a neighbour when the result still fits |
| "These ranges are typical, not predictions" sat alone at the end of the score-drop document | Moved into that document's intro; every range in the corpus is also labeled "typical" inline |
