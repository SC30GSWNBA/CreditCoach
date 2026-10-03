# CreditCoach

A chat assistant that helps first-time borrowers understand why their credit score changed and how to improve it steadily. It grounds every answer in credit-education content (RAG) and the user's own simulated account data. It never guarantees a score outcome, never recommends a predatory product, and never invents a figure.

All guidance is educational, not financial advice. All user data in this repo is synthetic.

**Status:** Week 1 (foundations, RAG and chat UI) is built, with a separate login for each of the 15 dataset users. See the [Week 1 tracker](docs/evidence/week-1/README.md). Week 2 (account tools through MCP, goal memory and the agent trace) is built, with Aman's and Anil's sign-off still to come: the tool specs (Task 12) are in [docs/tools.md](docs/tools.md), the score-history and account-summary tools (Tasks 13–14) are built and tested, and since Task 15 the chat reads each user's scores and accounts live through them over MCP. Since Tasks 16–17 every conversation is saved to that user's memory, which is shared through git, and answers recall the user's goal and earlier conversations (see [Memory](#memory)). Since Task 18 the chat shows live progress while an answer is being built, then an expandable agent trace of every tool call and the recalled goal. The [Week 2 tracker](docs/evidence/week-2/README.md) shows each task's status. Every Week 1–2 evaluation runs all 50 requirements.md queries (the 6 sample queries and the 44 additional ones), not just the original 6; see [Evaluation queries](#evaluation-queries). Known engineering gaps and the plan to close them are in the [Engineering Roadmap](#engineering-roadmap).

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

# 7. Ask CreditCoach (retrieval + GPT-5; needs your OpenRouter key). Add --user USR-001 to answer from that user's data via the MCP tools
uv run python -m creditcoach.agent.pipeline "why did my credit score drop 20 points?"

# 8. Open the chat UI at http://127.0.0.1:7860 (add --share for a public link) and sign in as one of the 15 users
uv run python -m creditcoach.app

# 9. Run the tests (no API key needed; CI runs them on every pull request)
uv run pytest
```

> **Share links are public.** Anyone with the link reaches the login page, and every answer uses your OpenRouter key. Stop the app (Ctrl+C) when you're done; the link closes with it. See [Chat UI logins](#chat-ui-logins).

You should see every line marked `[PASS]`, ending with `All checks passed. Ready to build.`

> The first `uv sync` downloads PyTorch for the local embedding model, so it can take a few minutes.

## What's Here

```
CreditCoach/
  creditcoach/        # Python package
    config.py         #   secrets, model IDs, paths (model IDs live here, not in code)
    check.py          #   setup check for fresh clones
    llm.py            #   OpenRouter client with fallback model
    auth.py           #   per-user chat UI logins (password hashes in app/logins.json)
    user_data.py      #   one signed-in user's profile, scores and accounts from data/, nobody else's
    prompts/          #   system_prompt.md (tone, India context, hard rules)
    rag/              #   corpus loader, ingestion (chunk, embed, store in .chroma/), retrieval (search + rerank)
    agent/            #   pipeline.py: question -> retrieval -> both tools prefetched over MCP -> agent loop -> grounded answer;
                      #   mcp_host.py: MCP client that runs tool calls for the signed-in user only (Task 15)
    tools/            #   data tools from docs/tools.md: score_history.py (Task 13), account_summary.py (Task 14); common.py (errors, data);
                      #   server.py: MCP server exposing both (Task 15): python -m creditcoach.tools.server
    app/              #   Gradio chat UI (Task 11): python -m creditcoach.app [--share]; logins.json;
                      #   trace.py: live progress and the expandable agent trace (Task 18)
    evals/            #   golden.py + golden_queries.json: the 50 requirements.md queries with their checks;
                      #   live.py: runs them through the agent and saves every answer (Tasks 5, 10, 15; Week 4)
    memory/           #   per-user memory: store.py (episodes, goal), dream.py (consolidation) (Task 16);
                      #   recall.py: MEMORY in each answer and the save_goal / clear_goal tools (Task 17)
  corpus/             # RAG corpus: 17 credit-education documents (see corpus/README.md)
  memory/             # each user's conversations and consolidated memory, committed (see memory/README.md)
  data/               # synthetic dataset: 15 users, accounts, score history (see data/README.md)
  tests/              # pytest tests (uv run pytest), run by CI (.github/workflows/tests.yml):
                      #   test_score_history.py, test_account_summary.py (Tasks 13–14), test_mcp.py (Task 15),
                      #   test_memory.py (Task 16), test_recall.py (Task 17), test_trace.py (Task 18),
                      #   test_golden_queries.py: every requirements.md figure checked against the tools,
                      #   test_llm.py: model client (output-token cap, fallback)
  scripts/
    synthetic/        #   step1-3: build data/ from the interviews and the sample
    task05_prompt_tests.py   # system prompt test runs (Task 5; --all: rule checks on all 50 answers)
    task07_corpus_report.py  # corpus validation and coverage of all 50 queries (Task 7)
    task08_ingestion_report.py # rebuild the vector store and regenerate the Task 8 evidence
    task09_retrieval_eval.py # retrieval test and strategy comparison, incl. all 50 queries (Task 9)
    task10_prototype_run.py  # prototype round trip with grounding checks (Task 10; --all: 50 queries)
    task11_login_isolation.py # per-user logins and data-isolation checks (Task 11 follow-up)
    task13_score_history_test.py # score-history tool test log (Task 13)
    task14_account_summary_test.py # account-summary tool test log (Task 14)
    task15_mcp_round_trip.py # live MCP round trip trace (Task 15; --all: 50 queries; paid model calls)
    task16_memory_record.py  # memory record written and read back, plus a live dream (Task 16)
    task17_goal_recall.py    # goal stated in session 1, recalled unprompted in session 2 (Task 17; paid calls)
    memory_sync.py           # share your chat memory as a PR (push), or pull everyone's (pull)
    set_login.py             # add or change a chat UI login
  user_interviews/    # 14 interview responses (dummy participants) used to build data/
  sample_data/        # original seed profile (USR-001) in xlsx, in USD
  docs/               # team.md, 6-pager.md, pr-faq.md, tools.md, memory.md, research/, evidence/week-1/ and week-2/
  tasks.md            # 4-week task plan with Definition of Done per task
  requirements.md     # product requirements, persona, sample and additional queries, guardrails
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

## Memory

CreditCoach remembers each user across sessions, machines and teammates (Task 16; schema in [docs/memory.md](docs/memory.md)):

- **Episodic:** every chat session is saved as it happens to `memory/<user_id>/episodes/`. Each one records the sign-in, every question and reply (with the tools and passages used, but never tool output), errors, and the sign-out or closed tab.
- **Semantic:** the user's goal (target score, target date, purpose), saved only by an explicit `goal_set` event in the user's own words, plus facts they've shared.
- **Procedural:** how the user likes to be helped, for example "keep answers short".
- **Dreaming:** when a user signs in, their earlier sessions are consolidated in the background into a new file in `memory/<user_id>/dreams/`. Duplicates are merged, stale or contradicted items dropped, and each session summarised. Dreaming never changes the goal and never stores a credit figure.

The chat's **Your memory and past conversations** panel shows the goal, the consolidated memory and earlier sessions, including teammates'. Since Task 17, every answer uses that memory. CreditCoach connects its advice to the stored goal without being asked, picks up where the last conversation ended, and saves a goal you state with its `save_goal` tool, in your own words. It changes a goal only when you explicitly ask.

**Sharing memory.** Every user is synthetic, so memory is committed to the repo. Files are append-only with unique names, so they never conflict. **Don't type real personal information in the chat.**

```bash
uv run python scripts/memory_sync.py              # share your new sessions: commits only memory/ and opens a PR
uv run python scripts/memory_sync.py pull         # after it merges: pull everyone's sessions (use this instead of git pull)
uv run python -m creditcoach.memory.dream --all   # consolidate by hand (normally runs at sign-in)
```

## Evaluation queries

requirements.md lists 50 queries with their expected behavior: 6 sample queries (§3) and 44 additional queries (§4) that vary them across users, figures and wording. They are one golden set, read by every evaluation so none of them drifts back to the original 6:

- **`creditcoach/evals/golden.py`** reads each query's text, user and expected behavior straight from requirements.md, so the set can't drift from it. **`golden_queries.json`** adds what code checks: the tools each query needs, the figures its answer relies on, answer keywords, forbidden patterns, and the later tasks a full check depends on (goal memory, multi-turn, observability).
- **CI** (`tests/test_golden_queries.py`): every expected figure (146 values) is read from the tools and compared, and the figures requirements.md derives from them (paydowns, total debt, gaps to a target) are recomputed. A dataset change that breaks requirements.md §4 fails the build.

| Task | What runs on all 50 queries | Command | Paid calls |
|---|---|---|---|
| 5 | System prompt hard rules checked on every live answer | `uv run python scripts/task05_prompt_tests.py --all` | none (reads the Task 15 run) |
| 7 | Corpus coverage: key facts for each query, and topics that must stay absent | `uv run python scripts/task07_corpus_report.py` | none |
| 8 | Chunk tags for all 50 queries in the vector store | `uv run python scripts/task08_ingestion_report.py` | none |
| 9 | Retrieval Hit@3, Precision@3 and MRR for four strategies | `uv run python scripts/task09_retrieval_eval.py` | none |
| 10 | Prototype answers with no user data | `uv run python scripts/task10_prototype_run.py --all` | 50 |
| 13–14 | Every figure each query relies on, from the tools | `uv run python scripts/task13_score_history_test.py` (and `task14_…`) | none |
| 15 | Full agent over MCP, each query signed in as its user; #45 with a forced tool timeout | `uv run python scripts/task15_mcp_round_trip.py --all` | about 100–150 |

The live checks are lenient keyword checks: they catch a missing figure or behavior, and the Task 27 judge scores tone and completeness.

## Configuration

All settings are read from `.env` (git-ignored). See [.env.example](.env.example).

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `OPENROUTER_API_KEY` | Yes | — | Access to all models through OpenRouter |
| `CHAT_MODEL` | No | `openai/gpt-5` | Main chat model |
| `SMALL_MODEL` | No | `openai/gpt-5-mini` | Cheap side calls (guardrail checks, eval judging) |
| `FALLBACK_MODEL` | No | `openai/gpt-4o` | Used when the chat model is slow or unavailable |
| `REASONING_EFFORT` | No | `low` | How long GPT-5 reasons before answering (`minimal`, `low`, `medium`, `high`). `low` keeps UI answers to about 8 s. |
| `MAX_OUTPUT_TOKENS` | No | `16000` | Cap on each reply's tokens, reasoning included. Without it OpenRouter reserves GPT-5's full 65,536 tokens, so a key with less credit than that gets a 402 and every answer silently comes from `FALLBACK_MODEL`. |
| `EMBEDDING_MODEL` | No | `sentence-transformers/all-MiniLM-L6-v2` | Local embedding model for the vector store. Rebuild the store after changing it. |
| `RERANKER_MODEL` | No | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Local cross-encoder that reorders retrieved chunks |

## Chat UI logins

The chat UI always asks for a login, locally and on a share link. There is one login per dataset user, and each answer uses **only that user's** profile, score history and accounts from `data/`:

| Username | Signs in as |
|---|---|
| `creditcoach_user1` | USR-001 (Aravind, the requirements.md persona) |
| `creditcoach_user2` … `creditcoach_user15` | USR-002 … USR-015, in order (see `data/users.csv`) |

- **Passwords** follow the pattern the team agreed and are shared privately, never in the repo. `creditcoach/app/logins.json` holds only a salted PBKDF2-SHA256 hash of each, so every clone accepts the same logins with no setup.
- **One user can't see another's data.** The user comes from the signed-in session, never from the message. Only that user's rows are loaded, and the system prompt tells the model to decline questions about anyone else. Checked in [task-11-user-logins.md](docs/evidence/week-1/task-11-user-logins.md).
- **Change a password or add a user:** `uv run python scripts/set_login.py USR-005 creditcoach_user5`, which asks for the password at a hidden prompt. Commit `logins.json` afterwards.
- **Sign out** with the **Log out** button at the top of the chat.

## Branch Strategy

We use **main + short-lived feature branches**, one branch per task.

- **`main`** always works and is protected on GitHub. Only the repo owner (Sudip, `@SC30GSWNBA`) can commit to it directly. Everyone else can pull from `main` but pushes only to a feature branch; GitHub rejects a direct push to `main`.
- **Feature branches** are named `week<N>/task-<NN>-<short-name>`, for example `week1/task-05-system-prompt` or `week2/task-13-score-history-tool`.
- **Pull requests:** open one per task, with the PR description linking the task's *Evidence of Completion*. A PR can merge only after Sudip approves it ([CODEOWNERS](.github/CODEOWNERS)); teammates' reviews are welcome but don't count as the approval. A new push to the branch dismisses an earlier approval. Merge with **squash merge** to keep `main` history to one commit per task.
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

A technical review after Week 1 found gaps in testing, tooling and robustness. This section tracks them alongside the [4-week plan](tasks.md). Items tied to a later task are built as part of that task. **Items 1 and 2 are started (Task 13), item 5 is started (the 50-query golden set), and item 11 is partly addressed (Task 18's live progress); the rest aren't started yet.**

### 1. Before Week 2: what technical reviewers check first

| # | Gap today | Plan |
|---|---|---|
| 1 | **No automated tests.** `pytest` is a dev dependency, but there's no `tests/` folder. | Unit tests for code that doesn't call the LLM: chunking (`rag/ingest.py`), `normalize_query`, front-matter parsing, `build_context`, and dataset consistency (every account and score row belongs to a known user). Mock `llm.chat` to test the pipeline's logic without API calls.<br><br>**Started (Tasks 13–18):** both data tools (`test_score_history.py`, `test_account_summary.py`), the MCP server and host (`test_mcp.py`), memory and dreaming validation (`test_memory.py`), goal recall and the goal tools (`test_recall.py`), the agent trace and streaming chat handler with `answer` mocked (`test_trace.py`), and every requirements.md figure (`test_golden_queries.py`). Still to do: chunking, `normalize_query`, front-matter parsing and `build_context`. |
| 2 | **No CI.** There's no `.github/workflows/`. | One GitHub Actions workflow on every PR: `uv sync`, lint, `creditcoach.check` and the tests. Add a build badge to this README once it passes.<br><br>**Started (Task 13):** `.github/workflows/tests.yml` runs `uv sync --frozen` and `pytest` on every PR and push to `main`. Still to do: lint, `creditcoach.check` (it needs an API key, so it would need a CI secret or a skip) and the badge. |
| 3 | **No lint, format or type-check config.** `.gitignore` lists `.ruff_cache/`, but ruff isn't configured. | Add `[tool.ruff]` and a type checker (mypy or pyright) to `pyproject.toml`, plus a `.pre-commit-config.yaml`. |
| 4 | **No LICENSE.** The repo is public, but without a license nobody can legally reuse or contribute to the code. | Add a LICENSE file (the team picks the license). |
| 5 | **Evals are one-off scripts, not a harness.** `scripts/task05…task10` write Markdown evidence, and the Task 5 and Task 10 judgments are filled in by a person (`_TBD_`). | A reusable eval suite with a golden set of questions (JSON or YAML), built from the 50 queries in requirements.md §3 and §4, and automatic scoring:<br>- **Retrieval:** Hit@k and MRR.<br>- **Guardrails:** refuses guarantees and predatory products; invents no numbers.<br>- **Answer quality:** an LLM judge using `SMALL_MODEL`, already set aside for this.<br><br>This is where Week 4's harness (Tasks 27–30) begins.<br><br>**Started (2026-10-02):** the golden set (`creditcoach/evals/`, see [Evaluation queries](#evaluation-queries)) with retrieval Hit@3 and MRR, keyword and figure checks, and a guarantee check, used by Tasks 5, 7, 9, 10, 13, 14 and 15, and saved live runs to score against. Still to do: the LLM judge and a one-command harness (Task 27). |
| 6 | **Regressions go unnoticed.** Nothing runs the evals when the prompt or model changes. | Run the retrieval evals in CI (local and free). Run the LLM evals on demand, because they cost API credits. |

### 2. Before and during Week 2: agent readiness and robustness

| # | Gap today | Plan |
|---|---|---|
| 7 | **No observability.** `llm.chat()` ignores `response.usage`, so tokens, cost and latency per call aren't recorded. | Log usage and latency for every call. Add tracing (Langfuse, LangSmith or OpenTelemetry) before the Week 2 tools arrive, because debugging tool calls without traces is painful. Task 26's trace IDs build on this. |
| 8 | **Fragile LLM client.** It catches a broad `except Exception` and tries the fallback model once. It has no retries, and it creates a new client on every call. | Catch specific exceptions, retry rate limits (429) and server errors (5xx) with backoff (for example `tenacity`), and reuse one client. Task 32 covers wider timeout handling. |
| 9 | **No architecture or design doc for Week 2.** The chat history was passed in but unused (used since Task 17). | Add a diagram of the pipeline and agent loop. The tool contracts are in [docs/tools.md](docs/tools.md) (Task 12), and the agent loop over MCP is described in `pipeline.py` and `mcp_host.py` (Task 15). Memory and recall are specified in [docs/memory.md](docs/memory.md) (Tasks 16–17). Still to write: one diagram of how retrieval, the MCP tools and memory meet in `pipeline.py`. |
| 10 | **Prompts aren't versioned.** `system_prompt.md` has no version, and answers don't record which prompt produced them. | Add a prompt version or hash to each `Answer` and to eval results, so a change in behaviour can be traced to a prompt change. |
| 11 | **No streaming.** The UI shows the whole answer at once, after about 18 s with GPT-5 (18.5 s in the Task 18 run: 0.1 s retrieval, the rest almost all the model). | Stream tokens into the chat window so answers start appearing right away.<br><br>**Partly addressed (Task 18):** while the user waits, the chat shows each step live with timers and rotating credit tips. The answer's words still arrive all at once. |

### 3. Nice to have: collaborator experience

| # | Gap today | Plan |
|---|---|---|
| 12 | **Setup takes several manual steps.** | Add a Dockerfile or devcontainer for one-command setup, which also makes the Task 34 deployment (for example Hugging Face Spaces or Render) straightforward. Use the CPU-only PyTorch index to shrink the large first download. |
| 13 | **Long commands.** | Add a Makefile or justfile with `setup`, `ingest`, `test`, `eval`, `app` and `lint`. |
| 14 | **No contributor files.** | Add:<br>- `CONTRIBUTING.md`, with the branch strategy moved there;<br>- `SECURITY.md`, covering how to report problems such as a leaked API key, and how data is handled;<br>- PR and issue templates;<br>- `CHANGELOG.md`. |

**Order:** do items 1–4 first. They're quick, they're what reviewers check first, and CI protects everything built after them. Do items 5–7 before Task 13, the first tool code (Task 12 is a written spec only): evals and tracing are much harder to add once tools and memory make the agent's behaviour complex. Items 8–11 harden the agent, and 12–14 are polish for collaborators.

## Troubleshooting

| Problem | Fix |
|---|---|
| `uv: command not found` | Install uv (see Prerequisites), then open a new terminal. |
| `[FAIL] OPENROUTER_API_KEY set in .env` | Run `cp .env.example .env` and put your real key in `.env`. |
| `[FAIL] Python >= 3.11` | Run `uv python install 3.12`, then `uv sync` again. Always run code with `uv run ...`, not a system `python`. |
| `[FAIL] import ...` | Run `uv sync` again from the repo root. |
| `[INFO] Vector store not built yet` | Run `uv run python -m creditcoach.rag.ingest`. |
| `[FAIL] Chat UI logins` or "No logins found" | Run `git pull`: `creditcoach/app/logins.json` must be present, with one login per user. |
| Login page says the credentials are wrong | Usernames are `creditcoach_user1` to `creditcoach_user15`, and passwords are case-sensitive. Ask the team for the current passwords. |
| `git pull` says "untracked working tree files would be overwritten" for files in `memory/` | Your shared sessions came back from GitHub. Run `uv run python scripts/memory_sync.py pull`, which removes only the identical local copies and then pulls. |
| Ingest or retrieve prints "unauthenticated requests to the HF Hub" | Harmless. The first ingest downloads the embedding model and the first retrieval downloads the reranker (each about 90 MB) from Hugging Face; later runs use the local copies. |

## Project Docs

- [tasks.md](tasks.md): 4-week plan and Definition of Done
- [requirements.md](requirements.md): persona, the 6 sample queries and 44 additional queries with expected behavior, constraints, guardrails
- [docs/team.md](docs/team.md): team, roles, and tech stack
- [docs/6-pager.md](docs/6-pager.md): narrative memo
- [docs/pr-faq.md](docs/pr-faq.md): press release and FAQ
- [docs/research/interview-questionnaire.md](docs/research/interview-questionnaire.md): 1:1 user interview questionnaire
- [docs/tools.md](docs/tools.md): specs for the `get_score_history` and `get_account_summary` tools (Task 12)
- [docs/memory.md](docs/memory.md): memory schema: episodes, the goal record, dreaming (Task 16)
- [data/README.md](data/README.md): synthetic dataset, how it's built, interview findings
- [docs/evidence/week-1/](docs/evidence/week-1/): evidence of completion for each Week 1 task
- [docs/evidence/week-2/](docs/evidence/week-2/): evidence of completion for each Week 2 task
