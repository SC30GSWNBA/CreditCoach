# CreditCoach

A chat assistant that helps first-time borrowers understand why their credit score changed and how to improve it steadily. It grounds every answer in credit-education content (RAG) and the user's own simulated account data. It never guarantees a score outcome, never recommends a predatory product, and never invents a figure.

All guidance is educational, not financial advice. All user data in this repo is synthetic.

**Status:** Week 1 (foundations, RAG and chat UI) is built. See the [Week 1 tracker](docs/evidence/week-1/README.md). Week 2 adds account tools (MCP) and goal memory. Known engineering gaps and the plan to close them are in the [Engineering Roadmap](#engineering-roadmap).

## Quickstart (fresh clone)

**Prerequisites:** git, and [uv](https://docs.astral.sh/uv/getting-started/installation/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`). You don't need to install Python separately: uv downloads Python 3.12 if you don't have it.

```bash
# 1. Clone
git clone https://github.com/SC30GSWNBA/CreditCoach.git
cd CreditCoach

# 2. Install Python 3.12 and all dependencies into .venv
uv sync

# 3. Add your OpenRouter API key
cp .env.example .env
#    then edit .env and set OPENROUTER_API_KEY (get one at https://openrouter.ai/keys)

# 4. Check your setup
uv run python -m creditcoach.check

# 5. Build the vector store from corpus/ (about 10 seconds; rerun after editing the corpus)
uv run python -m creditcoach.rag.ingest

# 6. Try retrieval
uv run python -m creditcoach.rag.retrieve "why did my credit score drop 20 points?"

# 7. Ask CreditCoach (retrieval + GPT-5; needs your OpenRouter key)
uv run python -m creditcoach.agent.pipeline "why did my credit score drop 20 points?"

# 8. Open the chat UI at http://127.0.0.1:7860 (add --share for a public link)
uv run python -m creditcoach.app
```

> **Share links are public.** Anyone with the link can chat, and every answer uses your OpenRouter key. Set `APP_USERNAME` and `APP_PASSWORD` in `.env` before using `--share`, and stop the app (Ctrl+C) when you're done; the link closes with it.

You should see every line marked `[PASS]`, ending with `All checks passed. Ready to build.`

> The first `uv sync` downloads PyTorch for the local embedding model, so it can take a few minutes.

## What's Here

```
CreditCoach/
  creditcoach/        # Python package
    config.py         #   secrets, model IDs, paths (model IDs live here, not in code)
    check.py          #   setup check for fresh clones
    llm.py            #   OpenRouter client with fallback model
    prompts/          #   system_prompt.md (tone, India context, hard rules)
    rag/              #   corpus loader, ingestion (chunk, embed, store in .chroma/), retrieval (search + rerank)
    agent/            #   pipeline.py: question -> retrieval -> grounded answer (Task 10 prototype)
    app/              #   Gradio chat UI (Task 11): python -m creditcoach.app [--share]
                      #   coming: tools/, memory/
  corpus/             # RAG corpus: 17 credit-education documents (see corpus/README.md)
  data/               # synthetic dataset: 13 users, accounts, score history (see data/README.md)
  scripts/
    synthetic/        #   step1-3: build data/ from the interviews and the sample
    task05_prompt_tests.py   # system prompt test runs (Task 5)
    task07_corpus_report.py  # corpus validation and coverage report (Task 7)
    task09_retrieval_eval.py # retrieval test and strategy comparison (Task 9)
    task10_prototype_run.py  # prototype round trip with grounding checks (Task 10)
  user_interviews/    # 12 interview responses (dummy participants) used to build data/
  sample_data/        # original seed profile (USR-001) in xlsx, in USD
  docs/               # team.md, 6-pager.md, pr-faq.md, research/, evidence/week-1/
  tasks.md            # 4-week task plan with Definition of Done per task
  requirements.md     # product requirements, persona, sample queries, guardrails
  credit_score_factors_guide.pdf   # seed document for the RAG corpus
```

**Context:** CreditCoach is built for Indian consumers. Amounts are in ₹, and scores use the 300–900 range of Indian credit bureaus (CIBIL, Experian, Equifax, CRIF High Mark).

**Rebuild the dataset** (deterministic, validated on every run):

```bash
uv run python scripts/synthetic/step1_profiles.py
uv run python scripts/synthetic/step2_accounts_scores.py
uv run python scripts/synthetic/step3_summary.py
```

**Stack:** Python 3.12 · OpenAI GPT-5 / GPT-4 models via OpenRouter · sentence-transformers (local embeddings) · ChromaDB · Gradio. See [docs/team.md](docs/team.md) for the full stack and the reasons behind each choice.

## Configuration

All settings are read from `.env` (git-ignored). See [.env.example](.env.example).

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `OPENROUTER_API_KEY` | Yes | — | Access to all models through OpenRouter |
| `CHAT_MODEL` | No | `openai/gpt-5` | Main chat model |
| `SMALL_MODEL` | No | `openai/gpt-5-mini` | Cheap side calls (guardrail checks, eval judging) |
| `FALLBACK_MODEL` | No | `openai/gpt-4o` | Used when the chat model is slow or unavailable |
| `REASONING_EFFORT` | No | `low` | How long GPT-5 reasons before answering (`minimal`, `low`, `medium`, `high`). `low` keeps UI answers to about 8 s. |
| `EMBEDDING_MODEL` | No | `sentence-transformers/all-MiniLM-L6-v2` | Local embedding model for the vector store. Rebuild the store after changing it. |
| `RERANKER_MODEL` | No | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Local cross-encoder that reorders retrieved chunks |
| `APP_USERNAME`, `APP_PASSWORD` | Recommended with `--share` | — | Login for the chat UI. Without both, the UI is open to anyone with the link. |

## Branch Strategy

We use **main + short-lived feature branches**, one branch per task.

- **`main`** always works. Nobody pushes to it directly. Changes arrive only through pull requests.
- **Feature branches** are named `week<N>/task-<NN>-<short-name>`, for example `week1/task-05-system-prompt` or `week2/task-13-score-history-tool`.
- **Pull requests:** open one per task. Another teammate reviews it, and the PR description links the task's *Evidence of Completion*. Merge with **squash merge** to keep `main` history to one commit per task.
- **Keep branches short:** merge within a day or two, and delete the branch after merging.
- **Commit messages** start with the task number: `Task 5: Add system prompt with no-guarantee rule`.

```bash
git switch main && git pull
git switch -c week1/task-05-system-prompt
# ...work, commit...
git push -u origin week1/task-05-system-prompt
# open a PR on GitHub, get a review, squash-merge
```

## Engineering Roadmap

A technical review after Week 1 found gaps in testing, tooling and robustness. This section tracks them alongside the [4-week plan](tasks.md). Items tied to a later task are built as part of that task. **None of these is done yet.**

### 1. Before Week 2: what technical reviewers check first

| # | Gap today | Plan |
|---|---|---|
| 1 | **No automated tests.** `pytest` is a dev dependency, but there's no `tests/` folder. | Unit tests for code that doesn't call the LLM: chunking (`rag/ingest.py`), `normalize_query`, front-matter parsing, `build_context`, and dataset consistency (every account and score row belongs to a known user). Mock `llm.chat` to test the pipeline's logic without API calls. |
| 2 | **No CI.** There's no `.github/workflows/`. | One GitHub Actions workflow on every PR: `uv sync`, lint, `creditcoach.check` and the tests. Add a build badge to this README once it passes. |
| 3 | **No lint, format or type-check config.** `.gitignore` lists `.ruff_cache/`, but ruff isn't configured. | Add `[tool.ruff]` and a type checker (mypy or pyright) to `pyproject.toml`, plus a `.pre-commit-config.yaml`. |
| 4 | **No LICENSE.** The repo is public, but without a license nobody can legally reuse or contribute to the code. | Add a LICENSE file (the team picks the license). |
| 5 | **Evals are one-off scripts, not a harness.** `scripts/task05…task10` write Markdown evidence, and the Task 5 and Task 10 judgments are filled in by a person (`_TBD_`). | A reusable eval suite with a golden set of questions (JSON or YAML) and automatic scoring:<br>- **Retrieval:** Hit@k and MRR.<br>- **Guardrails:** refuses guarantees and predatory products; invents no numbers.<br>- **Answer quality:** an LLM judge using `SMALL_MODEL`, already set aside for this.<br><br>This is where Week 4's harness (Tasks 27–30) begins. |
| 6 | **Regressions go unnoticed.** Nothing runs the evals when the prompt or model changes. | Run the retrieval evals in CI (local and free). Run the LLM evals on demand, because they cost API credits. |

### 2. Before and during Week 2: agent readiness and robustness

| # | Gap today | Plan |
|---|---|---|
| 7 | **No observability.** `llm.chat()` ignores `response.usage`, so tokens, cost and latency per call aren't recorded. | Log usage and latency for every call. Add tracing (Langfuse, LangSmith or OpenTelemetry) before the Week 2 tools arrive, because debugging tool calls without traces is painful. Task 26's trace IDs build on this. |
| 8 | **Fragile LLM client.** It catches a broad `except Exception` and tries the fallback model once. It has no retries, and it creates a new client on every call. | Catch specific exceptions, retry rate limits (429) and server errors (5xx) with backoff (for example `tenacity`), and reuse one client. Task 32 covers wider timeout handling. |
| 9 | **No architecture or design doc for Week 2.** `pipeline.py` is single-turn: the chat history is passed in but unused. | Add a diagram of today's pipeline and the planned agent loop. Write down how the MCP tools (Tasks 12–15) and goal memory (Tasks 16–17) plug into `pipeline.py`, so reviewers can see it will grow into a real agent loop. |
| 10 | **Prompts aren't versioned.** `system_prompt.md` has no version, and answers don't record which prompt produced them. | Add a prompt version or hash to each `Answer` and to eval results, so a change in behaviour can be traced to a prompt change. |
| 11 | **No streaming.** The UI shows the whole answer at once, after about 8 s. | Stream tokens into the chat window so answers start appearing right away. |

### 3. Nice to have: collaborator experience

| # | Gap today | Plan |
|---|---|---|
| 12 | **Setup takes several manual steps.** | Add a Dockerfile or devcontainer for one-command setup, which also makes the Task 34 deployment (for example Hugging Face Spaces or Render) straightforward. Use the CPU-only PyTorch index to shrink the large first download. |
| 13 | **Long commands.** | Add a Makefile or justfile with `setup`, `ingest`, `test`, `eval`, `app` and `lint`. |
| 14 | **No contributor files.** | Add:<br>- `CONTRIBUTING.md`, with the branch strategy moved there;<br>- `SECURITY.md`, covering how to report problems such as a leaked API key, and how data is handled;<br>- PR and issue templates;<br>- `CHANGELOG.md`. |

**Order:** do items 1–4 first. They're quick, they're what reviewers check first, and CI protects everything built after them. Do items 5–7 before Task 12: evals and tracing are much harder to add once tools and memory make the agent's behaviour complex. Items 8–11 harden the agent, and 12–14 are polish for collaborators.

## Troubleshooting

| Problem | Fix |
|---|---|
| `uv: command not found` | Install uv (see Prerequisites), then open a new terminal. |
| `[FAIL] OPENROUTER_API_KEY set in .env` | Run `cp .env.example .env` and put your real key in `.env`. |
| `[FAIL] Python >= 3.11` | Run `uv python install 3.12`, then `uv sync` again. Always run code with `uv run ...`, not a system `python`. |
| `[FAIL] import ...` | Run `uv sync` again from the repo root. |
| `[INFO] Vector store not built yet` | Run `uv run python -m creditcoach.rag.ingest`. |
| Ingest or retrieve prints "unauthenticated requests to the HF Hub" | Harmless. The first ingest downloads the embedding model and the first retrieval downloads the reranker (each about 90 MB) from Hugging Face; later runs use the local copies. |

## Project Docs

- [tasks.md](tasks.md): 4-week plan and Definition of Done
- [requirements.md](requirements.md): persona, sample queries, guardrails
- [docs/team.md](docs/team.md): team, roles, and tech stack
- [docs/6-pager.md](docs/6-pager.md): narrative memo
- [docs/pr-faq.md](docs/pr-faq.md): press release and FAQ
- [docs/research/interview-questionnaire.md](docs/research/interview-questionnaire.md): 1:1 user interview questionnaire
- [data/README.md](data/README.md): synthetic dataset, how it's built, interview findings
- [docs/evidence/week-1/](docs/evidence/week-1/): evidence of completion for each Week 1 task
