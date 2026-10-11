# CreditCoach

A chat assistant that helps first-time borrowers understand why their credit score changed and how to improve it steadily. It grounds every answer in credit-education content (RAG) and the user's own simulated account data. It never guarantees a score outcome, never recommends a predatory product, and never invents a figure.

All guidance is educational, not financial advice. All user data in this repo is synthetic.

**Status:** Week 1 (foundations, RAG and chat UI) is built, with a separate login for each of the 15 dataset users. See the [Week 1 tracker](docs/evidence/week-1/README.md). Week 2 (account tools through MCP, goal memory and the agent trace) is built, with Aman's and Anil's sign-off still to come: the tool specs (Task 12) are in [docs/tools.md](docs/tools.md), the score-history and account-summary tools (Tasks 13–14) are built and tested, and since Task 15 the chat reads each user's scores and accounts live through them over MCP. Since Tasks 16–17 every conversation is saved to that user's memory, which is shared through git, and answers recall the user's goal and earlier conversations (see [Memory](#memory)). Since Task 18 the chat shows live progress while an answer is being built, then an expandable agent trace of every tool call and the recalled goal. Beyond the task plan, a **My credit** tab charts the signed-in user's score story, card utilization (with a what-if pay-down slider, the tasks.md stretch goal) and what they owe, straight from the same two tools. Each chat answer also ends with a **confidence percentage** (with the reason), worked out by fixed checks on the finished answer with no extra model call; it shows how well the answer is backed by the user's data and the library, not whether it is right. The [Week 2 tracker](docs/evidence/week-2/README.md) shows each task's status. Week 3 has started: the guardrail rules are written down (Task 19, [docs/guardrails.md](docs/guardrails.md)), since Task 20 every question and every answer passes through a guardrail layer built with NVIDIA NeMo Guardrails, Task 21 tested it live and red-teamed it, since Task 22 repeated lookups and repeated questions are served from a Redis cache, Task 23 measured it (median 11.05 s uncached against 0.009 s cached), since Task 25 the chat shows a guardrail badge and a cache badge above every answer, and all 6 sample queries pass end to end against the expected-answers table ([Task 24](docs/evidence/week-3/task-24-sample-queries.md)) (see [Caching](#caching), [Guardrails](#guardrails) and the [Week 3 tracker](docs/evidence/week-3/README.md)). Every Week 1–2 evaluation, and the Task 20 guardrail run, uses all 50 requirements.md queries (the 6 sample queries and the 44 additional ones), not just the original 6; see [Evaluation queries](#evaluation-queries). Known engineering gaps and the plan to close them are in the [Engineering Roadmap](#engineering-roadmap).

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
    agent/            #   pipeline.py: question -> guardrail input rails -> retrieval -> both tools prefetched over MCP -> agent loop
                      #   -> guardrail output rails -> grounded answer;
                      #   mcp_host.py: MCP client that runs tool calls for the signed-in user only (Task 15)
    cache/            #   the cache (Task 22): backend.py (Redis, or memory without REDIS_URL), __init__.py (layers, TTLs,
                      #   logging, counters), answers.py (the semantic answer cache and its safety checks)
    guardrails/       #   the guardrail layer (Task 20), built with NeMo Guardrails: config/config.yml (which rails run),
                      #   config/rails.co (Colang flows), checks.py (the checks), rails.py (engine, pass / reframe / block, log)
    dataset.py        #   reads users, accounts and score history from Neon or data/ (same DataFrames either way)
    tools/            #   data tools from docs/tools.md: score_history.py (Task 13), account_summary.py (Task 14); common.py (errors, data);
                      #   server.py: MCP server exposing both (Task 15): python -m creditcoach.tools.server
    app/              #   Gradio chat UI (Task 11): python -m creditcoach.app [--share]; logins.json;
                      #   trace.py: live progress and the expandable agent trace (Task 18)
                      #   charts.py: the "My credit" tab: score story, card utilization what-if, what you owe
                      #   confidence.py: the confidence percentage under each answer (fixed checks, no model call)
                      #   badges.py: the guardrail and cache badges above each answer (Task 25)
    evals/            #   golden.py + golden_queries.json: the 50 requirements.md queries with their checks;
                      #   live.py: runs them through the agent and saves every answer (Tasks 5, 10, 15; Week 4);
                      #   red_team.json: 28 adversarial prompts and 4 benign controls for the guardrail layer (Task 21)
    memory/           #   per-user memory: store.py (episodes, goal), pg.py (Neon Postgres), dream.py (consolidation) (Task 16);
                      #   recall.py: MEMORY in each answer and the save_goal / clear_goal tools (Task 17)
  corpus/             # RAG corpus: 17 credit-education documents (see corpus/README.md)
  memory/             # archive of file-based memory from before the move to Neon (see memory/README.md)
  data/               # synthetic dataset: 15 users, accounts, score history (see data/README.md); a copy is in Neon
  tests/              # pytest tests (uv run pytest), run by CI (.github/workflows/tests.yml):
                      #   test_score_history.py, test_account_summary.py (Tasks 13–14), test_mcp.py (Task 15),
                      #   test_memory.py (Task 16), test_recall.py (Task 17), test_trace.py (Task 18),
                      #   test_badges.py (Task 25): the badges and the guardrail and cache steps in the trace,
                      #   test_cache.py (Task 22): both stores, every layer, when a stored answer may be served,
                      #   test_guardrails.py (Tasks 20–21): every check, the Colang rails, reframe and block, fail closed,
                      #   and the red-team set against the input rails,
                      #   test_charts.py: the My credit tab (charts, what-if, data isolation),
                      #   test_confidence.py: the confidence percentage under each answer,
                      #   test_golden_queries.py: every requirements.md figure checked against the tools,
                      #   test_llm.py: model client (output-token cap, fallback, token and cost tracking for Task 23),
                      #   test_dataset.py: dataset loader (backend choice, Neon unreachable)
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
    task20_guardrail_log.py  # guardrail layer live: log entries, 3 reframed responses, 50 saved answers (Task 20; paid calls)
    task21_guardrail_tests.py # the two required guardrail tests and the red-team set, live (Task 21; paid calls; --rescore: none)
    task22_cache_log.py      # the same question twice, live: cache miss, then hit (Task 22; paid calls)
    task23_cache_latency.py  # cache hit rate, latency and cost, cached vs. uncached (Task 23; paid calls; --report: none)
    task24_sample_queries.py # the 6 sample queries end to end through the chat UI functions, table filled in (Task 24; paid calls)
    task25_badges.py         # screenshots of the guardrail and cache badges in the real UI (Task 25; paid calls;
                             # run with: uv run --with playwright python scripts/task25_badges.py)
    memory_import.py         # copy file memory (the memory/ archive) into Neon; safe to re-run
    data_import.py           # load data/*.csv into Neon (replaces the copy there); run after rebuilding the dataset
    memory_sync.py           # files backend only: share memory files as a PR (push), or pull everyone's (pull)
    set_login.py             # add or change a chat UI login
  user_interviews/    # 14 interview responses (dummy participants) used to build data/
  sample_data/        # original seed profile (USR-001) in xlsx, in USD
  docs/               # team.md, 6-pager.md, pr-faq.md, tools.md, memory.md, guardrails.md, caching.md, research/, evidence/week-1/ to week-3/
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
uv run python scripts/data_import.py   # then refresh the copy in Neon, and restart the app
```

**Where the dataset lives.** With `DATABASE_URL` set, the app and the tools read users, accounts and score history from three tables in the same Neon database as memory (`dataset_users`, `dataset_accounts`, `dataset_score_history`). That copy is loaded from `data/*.csv`, which stay the reviewed source: change the data by rebuilding the CSVs in a pull request, then run `scripts/data_import.py`. Don't edit the Neon tables directly. `uv run python -m creditcoach.check` fails if Neon and the CSVs differ. Without `DATABASE_URL`, or with `CREDITCOACH_DATA_BACKEND=files`, everything reads the CSVs, and tests always do, so the golden queries are checked against the committed data.

**Stack:** Python 3.12 · OpenAI GPT-5 / GPT-4 models via OpenRouter · sentence-transformers (local embeddings) · ChromaDB · Neon Postgres (memory and the dataset copy) · NVIDIA NeMo Guardrails (guardrail layer) · Redis (cache) · Gradio · Plotly (My credit charts). See [docs/team.md](docs/team.md) for the full stack and the reasons behind each choice.

## Memory

CreditCoach remembers each user across sessions, machines and teammates (Task 16; schema in [docs/memory.md](docs/memory.md)):

- **Episodic:** every chat session is saved as it happens, one row per event in Neon Postgres. Each one records the sign-in, every question and reply (with the tools and passages used, but never tool output), errors, and the sign-out or closed tab.
- **Semantic:** the user's goal (target score, target date, purpose), saved only by an explicit `goal_set` event in the user's own words, plus facts they've shared.
- **Procedural:** how the user likes to be helped, for example "keep answers short".
- **Dreaming:** when a user signs in, their earlier sessions are consolidated in the background into a new dream. Duplicates are merged, stale or contradicted items dropped, and each session summarised. Dreaming never changes the goal and never stores a credit figure.

The chat's **Your memory and past conversations** panel shows the goal, the consolidated memory and earlier sessions, including teammates'. Since Task 17, every answer uses that memory. CreditCoach connects its advice to the stored goal without being asked, picks up where the last conversation ended, and saves a goal you state with its `save_goal` tool, in your own words. It changes a goal only when you explicitly ask.

**Where memory lives.** Memory is kept in a shared [Neon](https://neon.com) Postgres database (free plan). Every teammate and every deployment reads and writes the same history, with no pull requests. Put the connection string in `.env` as `DATABASE_URL` (ask a teammate for it; in the Neon console it is under **Connect**). Without `DATABASE_URL`, the app falls back to plain files in `memory/`, which tests always use. The files committed in `memory/` are the archive from before the move, and they are already in Neon. Memory is append-only in both: nothing is ever edited or deleted. **Don't type real personal information in the chat.**

```bash
uv run python scripts/memory_import.py --dry-run  # files -> Neon: list sessions that aren't in Neon yet
uv run python scripts/memory_import.py            # copy them (skips anything already there)
uv run python -m creditcoach.memory.dream --all   # consolidate by hand (normally runs at sign-in)
```

## Guardrails

Every question and every answer passes through a guardrail layer (Task 20; rules and design in [docs/guardrails.md](docs/guardrails.md)), built with NVIDIA NeMo Guardrails. The rails are declared in [creditcoach/guardrails/config/](creditcoach/guardrails/config/) and run our own checks:

- **On the question:** personal identifiers (PAN, Aadhaar, card and account numbers, phone, email, OTP and the like) are replaced by placeholders before retrieval, the model, memory or the logs see them. Attempts to switch the rules off or read the hidden prompt are noted for the model. A question about a predatory product also gets the product-risk passages from the library.
- **On the answer, before the user sees it:** no promised or predicted score, every figure traced to this turn's tool output or the library, product answers flag the risk and offer a safer alternative without endorsing, and nothing from the hidden prompt or about another user.
- **If a rule is broken:** the model rewrites its draft once with the problem named (**reframed**). If the rewrite still breaks a rule, the user gets a fixed safe message (**blocked**). The user never sees the draft.

In the chat, a badge above each answer says what the layer did: passed, high-risk product not endorsed, no guarantee given, answer rewritten or answer blocked, with the reason ([screenshots](docs/evidence/week-3/task-25-badges.md)). The agent trace has a matching step. Each decision is also one JSON line on the `creditcoach.guardrails` logger. The fixed checks take under 0.1 s; a small-model wording review runs only on projections and product-related answers and adds about 2 s. Live log entries and three reframed responses are in [task-20-guardrail-log.md](docs/evidence/week-3/task-20-guardrail-log.md).

The layer is tested live on the two questions tasks.md names (the payday loan and the 720 guarantee) and red-teamed with 28 adversarial prompts in seven attack types: prompt injection, prompt leaking, PII insertion, indirect guarantees, indirect endorsements, fabrication bait and other users' data (Task 21; [results](docs/evidence/week-3/task-21-guardrail-tests.md)). The prompts are in `creditcoach/evals/red_team.json`. Add your own there: anything that gets through becomes a fix and a regression test.

```bash
uv run pytest tests/test_guardrails.py -v          # no API key needed
uv run python scripts/task20_guardrail_log.py      # live; regenerates the evidence (paid model calls)
uv run python scripts/task21_guardrail_tests.py    # live; required tests and the red-team set (paid model calls)
```

## Caching

Repeated work is served from a cache instead of being done again (Task 22; design in [docs/caching.md](docs/caching.md)):

| Layer | What is reused | Kept for |
|---|---|---|
| Embedding | A question's embedding vector | 7 days |
| Retrieval | The passages retrieved for a question | 24 hours |
| Tool | A user's score-history or account lookup | 5 minutes |
| Answer | A finished answer, when the same user asks the same question again | 1 hour |

The answer layer is the one you can see, and the chat marks it with a badge above the answer ("⚡ Cache hit · saved 7 s", "Cache miss · answered live" or "Cache not used" with the reason): a repeated question comes back in about 0.01 s instead of about 11 s, with no model call ([miss then hit](docs/evidence/week-3/task-22-cache-log.md); [measured](docs/evidence/week-3/task-23-cache-latency.md): median 11.05 s uncached against 0.009 s cached, and $0.012 of model cost against none). A stored answer is served only to the user who asked, only for the same question (exact, the same words reordered, or a rewording a small model confirms), and only after that user's live figures are checked to be unchanged. Questions that differ in a number, a "not" or a time word ("this month" and "last month") are never matched, however similar they look.

The cache is kept in Redis when `REDIS_URL` is set in `.env`:

```bash
brew install redis && brew services start redis     # then set REDIS_URL=redis://localhost:6379/0 in .env
```

Without `REDIS_URL` it is kept in the app's own memory and lost on restart, so a fresh clone needs no Redis. `CREDITCOACH_CACHE=off` turns it off. A Redis that is down never breaks an answer: lookups count as misses. To empty the cache: `uv run python -c "from creditcoach import cache; print(cache.clear())"`.

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
| 20 | The guardrail layer's fixed rails on the 50 answers saved by the Task 15 run | `uv run python scripts/task20_guardrail_log.py` | about 20 (its own live questions; the 50 answers are read from the saved run) |

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
| `REDIS_URL` | No | (none) | Redis connection string for the cache, for example `redis://localhost:6379/0`. Without it the cache is kept in the app's memory. |
| `CREDITCOACH_CACHE` | No | `on` | `off` turns every cache layer off |
| `CREDITCOACH_CACHE_CONFIRM` | No | `on` | `off` stops the answer cache asking `SMALL_MODEL` whether a reworded question is the same |
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

A technical review after Week 1 found gaps in testing, tooling and robustness. This section tracks them alongside the [4-week plan](tasks.md). Items tied to a later task are built as part of that task. **Items 1 and 2 are started (Task 13), item 5 is started (the 50-query golden set and the Week 3 red-team set), item 7 is partly addressed (Task 23's token and cost tracking), and item 11 is partly addressed (Task 18's live progress); the rest aren't started yet.**

### 1. Before Week 2: what technical reviewers check first

| # | Gap today | Plan |
|---|---|---|
| 1 | **No automated tests.** `pytest` is a dev dependency, but there's no `tests/` folder. | Unit tests for code that doesn't call the LLM: chunking (`rag/ingest.py`), `normalize_query`, front-matter parsing, `build_context`, and dataset consistency (every account and score row belongs to a known user). Mock `llm.chat` to test the pipeline's logic without API calls.<br><br>**Started (Tasks 13–18):** both data tools (`test_score_history.py`, `test_account_summary.py`), the MCP server and host (`test_mcp.py`), memory and dreaming validation (`test_memory.py`), goal recall and the goal tools (`test_recall.py`), the agent trace and streaming chat handler with `answer` mocked (`test_trace.py`), and every requirements.md figure (`test_golden_queries.py`). **Week 3 (Tasks 20–25):** the guardrail checks, rails and red-team set (`test_guardrails.py`), every cache layer (`test_cache.py`), the badges (`test_badges.py`), and the model client (`test_llm.py`), all with the model mocked. Still to do: chunking, `normalize_query`, front-matter parsing and `build_context`. |
| 2 | **No CI.** There's no `.github/workflows/`. | One GitHub Actions workflow on every PR: `uv sync`, lint, `creditcoach.check` and the tests. Add a build badge to this README once it passes.<br><br>**Started (Task 13):** `.github/workflows/tests.yml` runs `uv sync --frozen` and `pytest` on every PR and push to `main`. Still to do: lint, `creditcoach.check` (it needs an API key, so it would need a CI secret or a skip) and the badge. |
| 3 | **No lint, format or type-check config.** `.gitignore` lists `.ruff_cache/`, but ruff isn't configured. | Add `[tool.ruff]` and a type checker (mypy or pyright) to `pyproject.toml`, plus a `.pre-commit-config.yaml`. |
| 4 | **No LICENSE.** The repo is public, but without a license nobody can legally reuse or contribute to the code. | Add a LICENSE file (the team picks the license). |
| 5 | **Evals are one-off scripts, not a harness.** `scripts/task05…task10` write Markdown evidence, and the Task 5 and Task 10 judgments are filled in by a person (`_TBD_`). | A reusable eval suite with a golden set of questions (JSON or YAML), built from the 50 queries in requirements.md §3 and §4, and automatic scoring:<br>- **Retrieval:** Hit@k and MRR.<br>- **Guardrails:** refuses guarantees and predatory products; invents no numbers.<br>- **Answer quality:** an LLM judge using `SMALL_MODEL`, already set aside for this.<br><br>This is where Week 4's harness (Tasks 27–30) begins.<br><br>**Started (2026-10-02):** the golden set (`creditcoach/evals/`, see [Evaluation queries](#evaluation-queries)) with retrieval Hit@3 and MRR, keyword and figure checks, and a guarantee check, used by Tasks 5, 7, 9, 10, 13, 14 and 15, and saved live runs to score against. **Week 3:** the guardrail checks run on every answer, a red-team set of 28 adversarial prompts with a small-model judge (Task 21), and the six sample queries scored against the expected-answers table (Task 24). Still to do: a one-command harness over all 50 queries (Task 27). |
| 6 | **Regressions go unnoticed.** Nothing runs the evals when the prompt or model changes. | Run the retrieval evals in CI (local and free). Run the LLM evals on demand, because they cost API credits. |

### 2. Before and during Week 2: agent readiness and robustness

| # | Gap today | Plan |
|---|---|---|
| 7 | **No observability.** `llm.chat()` ignores `response.usage`, so tokens, cost and latency per call aren't recorded. | Log usage and latency for every call. Add tracing (Langfuse, LangSmith or OpenTelemetry) before the Week 2 tools arrive, because debugging tool calls without traces is painful. Task 26's trace IDs build on this.<br><br>**Partly addressed (Task 23):** `llm.track()` collects each call's model, tokens and cost, and the cache, guardrail and tool layers each log one JSON line per event. Still to do: record usage for every request (not only inside `track()`), and tracing with a shared trace ID (Task 26). |
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
| The cache badge never shows a hit after restarting the app | Without `REDIS_URL` the cache is kept in the app's memory and lost on restart, and a Redis that is down counts every lookup as a miss. Run `brew services start redis` and set `REDIS_URL` in `.env`; `uv run python -m creditcoach.check` says where the cache is kept. |
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
- [docs/caching.md](docs/caching.md): what is cached, where, for how long, and when a stored answer may be served (Task 22)
- [docs/guardrails.md](docs/guardrails.md): guardrail rules mapped to requirements.md (Task 19) and how the guardrail layer enforces them (Task 20)
- [data/README.md](data/README.md): synthetic dataset, how it's built, interview findings
- [docs/evidence/week-1/](docs/evidence/week-1/): evidence of completion for each Week 1 task
- [docs/evidence/week-2/](docs/evidence/week-2/): evidence of completion for each Week 2 task
- [docs/evidence/week-3/](docs/evidence/week-3/): evidence of completion for each Week 3 task
