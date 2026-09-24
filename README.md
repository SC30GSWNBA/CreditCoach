# CreditCoach

A chat assistant that helps first-time borrowers understand why their credit score changed and how to improve it steadily. It grounds every answer in credit-education content (RAG) and the user's own simulated account data. It never guarantees a score outcome, never recommends a predatory product, and never invents a figure.

All guidance is educational, not financial advice. All user data in this repo is synthetic.

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
```

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
    rag/              #   corpus loader and ingestion (chunk, embed, store in .chroma/)
                      #   coming: agent/, tools/, memory/, app/
  corpus/             # RAG corpus: 17 credit-education documents (see corpus/README.md)
  data/               # synthetic dataset: 13 users, accounts, score history (see data/README.md)
  scripts/
    synthetic/        #   step1-3: build data/ from the interviews and the sample
    task05_prompt_tests.py   # system prompt test runs (Task 5)
    task07_corpus_report.py  # corpus validation and coverage report (Task 7)
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

## Troubleshooting

| Problem | Fix |
|---|---|
| `uv: command not found` | Install uv (see Prerequisites), then open a new terminal. |
| `[FAIL] OPENROUTER_API_KEY set in .env` | Run `cp .env.example .env` and put your real key in `.env`. |
| `[FAIL] Python >= 3.11` | Run `uv python install 3.12`, then `uv sync` again. Always run code with `uv run ...`, not a system `python`. |
| `[FAIL] import ...` | Run `uv sync` again from the repo root. |

## Project Docs

- [tasks.md](tasks.md): 4-week plan and Definition of Done
- [requirements.md](requirements.md): persona, sample queries, guardrails
- [docs/team.md](docs/team.md): team, roles, and tech stack
- [docs/6-pager.md](docs/6-pager.md): narrative memo
- [docs/pr-faq.md](docs/pr-faq.md): press release and FAQ
- [docs/research/interview-questionnaire.md](docs/research/interview-questionnaire.md): 1:1 user interview questionnaire
- [data/README.md](data/README.md): synthetic dataset, how it's built, interview findings
- [docs/evidence/week-1/](docs/evidence/week-1/): evidence of completion for each Week 1 task
