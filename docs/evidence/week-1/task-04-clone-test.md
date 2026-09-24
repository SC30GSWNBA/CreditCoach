# Task 4 Evidence: Fresh-Clone Test

*2026-09-23 · Local dry run before the remote exists. The Definition of Done also needs a teammate to clone from GitHub and run it.*

Steps followed, from the README only:

```
git clone <repo> clone-test && cd clone-test
uv sync
cp .env.example .env        # dummy key used; the check only confirms a key is set
uv run python -m creditcoach.check
```

Output:

```
[PASS] Python >= 3.11 - 3.12.0
[PASS] import openai
[PASS] import dotenv
[PASS] import pandas
[PASS] import openpyxl
[PASS] import chromadb
[PASS] import sentence_transformers
[PASS] import gradio
[PASS] OPENROUTER_API_KEY set in .env - sk-or-du...
       models: chat=openai/gpt-5 small=openai/gpt-5-mini fallback=openai/gpt-4o
[PASS] Sample data readable - 1 user(s), 12 score rows, 5 accounts; latest USR-001 score 650 (Hard inquiry + utilization spike)

All checks passed. Ready to build.
```

> **Note (after Task 6):** the last check line now reads `[PASS] Dataset readable (data/) - 13 users, 25 accounts, 132 score rows; ...` because the check validates the synthetic dataset instead of the sample workbook. Since Task 8 it also prints `[INFO] Vector store built - 45 chunks ...` (or `[INFO] Vector store not built yet ...` before you run `uv run python -m creditcoach.rag.ingest`); this line is informational and never fails the check.

## Teammate verification (to fill in)

| Teammate | Cloned from GitHub | `uv sync` OK | Check passed | Date |
|---|---|---|---|---|
| Aman | [ ] | [ ] | [ ] | |
| Anik | [ ] | [ ] | [ ] | |
