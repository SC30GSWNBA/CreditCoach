# CreditCoach: Team, Roles & Tech Stack

*Week 1 · Task #1 (Kickoff) · Last updated: 2026-10-08 (memory and dataset in Neon Postgres)*

## 1. Roles

Each role owns its area end to end across all four weeks: design, build, tests, and demo evidence. The owner doesn't have to do all the work, but they answer for it being done.

| Role | Owner | Owns (tasks in `tasks.md`) | Week it matters most |
|---|---|---|---|
| **Prompt / RAG** | Aman / Anil / Sudip | System prompt (#5), corpus (#7), ingestion (#8), retrieval (#9), prototype (#10) | Week 1 |
| **Tools / MCP** | Aman / Anil / Sudip | Synthetic dataset (#6), tool specs (#12), score-history + account-summary tools (#13–14), MCP wiring (#15) | Week 2 |
| **Memory** | Aman / Anil / Sudip | Memory schema (#16), cross-session goal recall (#17) | Week 2 |
| **Guardrails / Caching** | Aman / Anil / Sudip | Guardrail rules + checks + tests (#19–21), caching + latency (#22–23) | Week 3 |
| **Observability / UI** | Aman / Anil / Sudip | Gradio UI (#11, #18, #25), tracing (#26), dashboard (#31) | Weeks 1, 2 & 4 |
| **Shared (all)** | Everyone | 6-pager (#2), PR/FAQ (#3), repo setup (#4), E2E run (#24), evals (#27–30), edge cases (#32), demo (#33–34) | — |

> All roles and tasks are shared by Aman, Anil and Sudip. There are no individual role leads.

## 2. Tech Stack (agreed)

| Layer | Choice | Why |
|---|---|---|
| Language | **Python 3.12** (pinned in `.python-version`; `pyproject.toml` allows 3.11+) | Gradio, Chroma, and the MCP SDK all need 3.10+. The system Python is 3.9.6, so always run code through `uv run`, which uses the pinned 3.12. |
| Env / packages | **uv** + `pyproject.toml` | Fast, reproducible installs, which a fresh clone needs (Task #4). |
| LLM | **OpenAI GPT-5 and GPT-4 family, called through OpenRouter.** We use the `openai` Python SDK pointed at `base_url="https://openrouter.ai/api/v1"`. **GPT-5** (`openai/gpt-5`) is the main chat model. **GPT-5 mini** (`openai/gpt-5-mini`) or **GPT-4.1 mini** (`openai/gpt-4.1-mini`) handles cheap side calls: guardrail classification and eval judging. **GPT-4o** (`openai/gpt-4o`) is the fallback if GPT-5 is slow or rate-limited. Model IDs live in config, not code. GPT-5 runs at `REASONING_EFFORT=low` (Task #11): about 8 s per answer instead of 14–37 s, with the same grounding. | One OpenRouter key gives access to every model, so we can switch models per call to compare cost and latency (stretch goal). OpenAI function calling maps cleanly onto MCP tools. |
| Embeddings | **sentence-transformers** `all-MiniLM-L6-v2` (local) | Free, offline, fast. The corpus is small, so there's no API cost or key needed for ingestion. |
| Reranker | **cross-encoder** `ms-marco-MiniLM-L-6-v2` (local), reorders the 12 nearest chunks | Chosen in Task #9: it put the most relevant chunk first far more often than embedding search alone (MRR 0.95 vs 0.83 on 10 labelled queries). |
| Vector store | **ChromaDB** (persistent, local `./.chroma/`) | Zero-ops, runs embedded in Python, and supports metadata filters (e.g., `category=product_risk`). |
| RAG orchestration | **Plain Python** (no LangChain/LlamaIndex) | The pipeline is small. Fewer abstractions make it easier to debug retrieval misses in Week 4 error analysis. |
| Tools / MCP | **`mcp` Python SDK v2 (`MCPServer`, called FastMCP in v1)** server exposing `get_score_history` and `get_account_summary` over stdio; the agent connects as an MCP client (Task 15) | Required by Week 2. Each MCP tool is a few lines wrapping the Task 13–14 functions. We use v2 (2.2 at the time of Task 15) rather than pinning v1. |
| Data | **pandas** over the synthetic dataset (15 users, Indian context: ₹ amounts, 300–900 score range). The app reads a copy in **Neon Postgres** (`dataset_*` tables, loaded by `scripts/data_import.py`); `data/*.csv` stay the reviewed source, and tests read them (`creditcoach/dataset.py`) | Built in Task #6 from the sample workbook and 14 user interviews. See `data/README.md`. Neon gives every teammate and deployment the same copy; `creditcoach.check` fails if it drifts from the CSVs. |
| Memory | **Append-only tables in Neon Postgres** (since 2026-10-07; Task #16 started with JSON files in `memory/<user_id>/`, kept as the archive and the backend tests use): one episode per chat session (logins, messages, replies, explicit `goal_set` events, logouts) and consolidated "dreams" with facts, preferences and session summaries. The goal (`target_score`, `target_date`, `purpose`) is replayed from `goal_set` events. Schema: [memory.md](memory.md) | Every teammate and deployment reads and writes the same history with no pull requests, and it survives a redeploy. A trigger refuses UPDATE and DELETE, as the never-edited files did. Replaces the SQLite plan from kickoff, then the git-committed files. |
| Caching | **Redis** (`redis-py`; the app's own memory when `REDIS_URL` isn't set): exact-match caches for embeddings, retrieval results and tool lookups, and a semantic cache of finished answers per user | Gives a persistent cache hit or miss we can log and badge in the UI (Task #25), shared between processes. Design in [caching.md](caching.md). |
| Guardrails | **NVIDIA NeMo Guardrails** (Colang flows) running our own checks as actions: regex/keyword checks, a figure-provenance check against tool output, and one small-model wording review (GPT-5 mini) | Maps one-to-one to requirements.md §6 ([guardrails.md](guardrails.md)). The rails are declared in a Colang file anyone can read, and every check is our own code, so nothing is a black box. |
| Observability | Structured JSON logs with a per-request `trace_id`, written to SQLite, plus a Gradio "Dashboard" tab | Meets §6 (tool-failure rate, graceful degradation) with no extra infrastructure. |
| Evals | **pytest** with custom scorers over the 6 sample queries (requirements.md §3) and the 44 additional queries (§4). The 50 queries are one golden set: `creditcoach/evals/golden.py` reads the text from requirements.md and the checks from `golden_queries.json` | One command (Task #27). The golden set already drives the Week 1–2 evaluations, and `tests/test_golden_queries.py` checks every expected figure against the tools in CI. |
| UI | **Gradio** `ChatInterface`, `launch(share=True)`, with one login per dataset user (`creditcoach/auth.py`); a "My credit" tab draws the score story with **Plotly** (`creditcoach/app/charts.py`) | Gives the shareable link Task #11 requires. Each login sees only its own user's data, so any teammate can demo any of the 15 users. |
| Secrets | `.env` (git-ignored) with `OPENROUTER_API_KEY` and the Neon `DATABASE_URL`, loaded by `python-dotenv`. `.env.example` is committed with a placeholder value. Chat UI passwords are committed only as salted PBKDF2 hashes (`creditcoach/app/logins.json`) and shared privately | Keys and passwords are never committed. |

### Repo layout

See the README for the current layout. Code lives in the `creditcoach/` Python package, with one subpackage per area added as each task starts: `prompts/` (system prompt), `agent/` (orchestration), `rag/` (corpus loader, ingestion, retrieval), `tools/` (MCP server and tools), `memory/` (episodes, goal, dreaming), `guardrails/` (the guardrail layer), `cache/` (the cache), `evals/` (the golden queries and the red-team set), and `app/` (Gradio UI). Content and data sit at the repo root: `corpus/` (RAG documents), `data/` (synthetic dataset), and `docs/`.

## 3. Kickoff Review: Key Takeaways from requirements.md

**Customer: Aravind.** Aravind is 22, in their first full-time job, and has had their first credit card for 8 months. Their score just dropped 20 points and they panicked. They're saving for a car and want plain-language answers grounded in their own account data, not generic blog advice. They also want a clear warning about "quick fixes" like payday loans and credit-repair services.

**What we're building:** an assistant that combines three things:
1. **RAG** over scoring-factor, financial-literacy, and product-risk content
2. **Tools** that read simulated score history and account data
3. **Memory** of the user's goal (target score, target date, purpose) across sessions

**Non-negotiable guardrails (§6):** these drive design choices from Week 1, not just Week 3.
1. Never guarantee a score outcome or timeline. Frame every projection as educational.
2. Never endorse predatory products (payday loans, guaranteed credit repair, advance-fee scams), and proactively flag them.
3. Never fabricate figures. Every score, balance, or factor must come from a live tool call.
4. Never silently override the user's stored goal.
5. Track tool-call failures and degrade gracefully ("here's what I last confirmed").

**Our acceptance bar:** the 6 sample queries in requirements.md §3. They become the eval suite in Task #27. The 44 additional queries in requirements.md §4 test the same behaviors with other users, figures, and wording, so the suite catches answers that only pass the original 6. Every Week 1 and Week 2 evaluation runs all 50 of them.

**What the sample data already shows (`sample_data/credit_profile_sample.xlsx`):**
- USR-001's score went from 690 (Jul 2026) to 670 (Aug, *utilization spike*) and then to 650 (Sep, *hard inquiry + utilization spike*). The Sep drop is exactly the "20 points this month" in sample query #1.
- Revolving accounts (amounts in ₹ after the Task #6 conversion to an Indian context): credit card ACC-01 is at ₹59,000 / ₹75,000 = **79% utilization**, credit card ACC-02 is at ₹11,000 / ₹1,00,000 = 11%, and card ACC-05 is at ₹4,750 / ₹25,000 = 19%. Overall revolving utilization is ₹74,750 / ₹2,00,000 = **37.4%**.
- Installment loans (no limit, so not part of utilization): education loan ACC-03 has a ₹4,20,000 balance and auto loan ACC-04 has a ₹3,05,000 balance.
- `credit_score_factors_guide.pdf` explains both causes: a utilization spike above 30% typically costs 10 to 40 points, and a hard inquiry costs 2 to 10. It also covers payday loans and credit-repair red flags. This makes it the seed document for the RAG corpus (Task #7).

## 4. Working Agreements

- **Definition of Done** comes from the `tasks.md` column. A task is not done until its *Evidence of Completion* artifact is in the repo.
- Evidence (logs, transcripts, screenshots) goes in `docs/evidence/week-N/`.
- A task moves forward only after the team signs off on the previous task's evidence.
- All guidance the product gives is educational. No real financial advice, loan origination, or credit repair (requirements.md §5).

## 5. Sign-off: "I have read requirements.md"

Each member checks their box and adds the date.

| Member | Role | Read requirements.md | Agree to stack | Date |
|---|---|---|---|---|
| Aman | All roles (shared) | [ ] | [ ] | |
| Anil | All roles (shared) | ✅ | ✅ | 2026-09-30 |
| Sudip | All roles (shared) | ✅ | ✅ | 2026-09-30 |

## 6. Action Items

| # | Action | Owner | Due | Status |
|---|---|---|---|---|
| 1 | Replace the 15 chat UI passwords with strong, random ones before sharing a link outside the team. Today's passwords follow a guessable pattern, and Gradio doesn't limit login attempts, so anyone with a share link could guess them. Decide how the new passwords are created (`scripts/set_login.py`) and shared privately. For now the link is shared only within the team. | Aman, Anil, Sudip | Before the final demo (Task 34) | ⬜ Open |
