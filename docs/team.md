# CreditCoach: Team, Roles & Tech Stack

*Week 1 · Task #1 (Kickoff) · Last updated: 2026-09-23*

## 1. Roles

Each role owns its area end to end across all four weeks: design, build, tests, and demo evidence. The owner doesn't have to do all the work, but they answer for it being done.

| Role | Owner | Owns (tasks in `tasks.md`) | Week it matters most |
|---|---|---|---|
| **Prompt / RAG** | Aman / Anik / Sudip | System prompt (#5), corpus (#7), ingestion (#8), retrieval (#9), prototype (#10) | Week 1 |
| **Tools / MCP** | Aman / Anik / Sudip | Synthetic dataset (#6), tool specs (#12), score-history + account-summary tools (#13–14), MCP wiring (#15) | Week 2 |
| **Memory** | Aman / Anik / Sudip | Memory schema (#16), cross-session goal recall (#17) | Week 2 |
| **Guardrails / Caching** | Aman / Anik / Sudip | Guardrail rules + checks + tests (#19–21), caching + latency (#22–23) | Week 3 |
| **Observability / UI** | Aman / Anik / Sudip | Gradio UI (#11, #18, #25), tracing (#26), dashboard (#31) | Weeks 1 & 4 |
| **Shared (all)** | Everyone | 6-pager (#2), PR/FAQ (#3), repo setup (#4), E2E run (#24), evals (#27–30), edge cases (#32), demo (#33–34) | — |

> All roles and tasks are shared by Aman, Anik and Sudip. There are no individual role leads.

## 2. Tech Stack (agreed)

| Layer | Choice | Why |
|---|---|---|
| Language | **Python 3.12** (pinned in `.python-version`; `pyproject.toml` allows 3.11+) | Gradio, Chroma, and the MCP SDK all need 3.10+. The system Python is 3.9.6, so always run code through `uv run`, which uses the pinned 3.12. |
| Env / packages | **uv** + `pyproject.toml` | Fast, reproducible installs, which a fresh clone needs (Task #4). |
| LLM | **OpenAI GPT-5 and GPT-4 family, called through OpenRouter.** We use the `openai` Python SDK pointed at `base_url="https://openrouter.ai/api/v1"`. **GPT-5** (`openai/gpt-5`) is the main chat model. **GPT-5 mini** (`openai/gpt-5-mini`) or **GPT-4.1 mini** (`openai/gpt-4.1-mini`) handles cheap side calls: guardrail classification and eval judging. **GPT-4o** (`openai/gpt-4o`) is the fallback if GPT-5 is slow or rate-limited. Model IDs live in config, not code. | One OpenRouter key gives access to every model, so we can switch models per call to compare cost and latency (stretch goal). OpenAI function calling maps cleanly onto MCP tools. |
| Embeddings | **sentence-transformers** `all-MiniLM-L6-v2` (local) | Free, offline, fast. The corpus is small, so there's no API cost or key needed for ingestion. |
| Vector store | **ChromaDB** (persistent, local `./.chroma/`) | Zero-ops, runs embedded in Python, and supports metadata filters (e.g., `category=product_risk`). |
| RAG orchestration | **Plain Python** (no LangChain/LlamaIndex) | The pipeline is small. Fewer abstractions make it easier to debug retrieval misses in Week 4 error analysis. |
| Tools / MCP | **`mcp` Python SDK (FastMCP)** server exposing `get_score_history` and `get_account_summary` | Required by Week 2. FastMCP keeps each tool to about 10 lines. |
| Data | **pandas + openpyxl** reading the synthetic dataset (seeded from `sample_data/credit_profile_sample.xlsx`) | The sample data is already in xlsx. We extend it with more profiles in Task #6. |
| Memory | **SQLite** (`memory.db`), one row per user goal: `target_score`, `target_date`, `purpose` | Persists across sessions and processes with no server. Easy to inspect for evidence. |
| Caching | **diskcache** for embeddings and tool lookups, keyed by a hash of the normalized query | Gives a persistent cache hit or miss we can log and badge in the UI (Task #25). |
| Guardrails | Custom rule layer: regex/keyword pre-check, a small-model classifier (GPT-5 mini / GPT-4.1 mini), and a figure-provenance check against tool output | Maps one-to-one to requirements.md §5. No black-box dependency. |
| Observability | Structured JSON logs with a per-request `trace_id`, written to SQLite, plus a Gradio "Dashboard" tab | Meets §5 (tool-failure rate, graceful degradation) with no extra infrastructure. |
| Evals | **pytest** with custom scorers over the 6 sample queries | One command: `uv run pytest evals/` (Task #27). |
| UI | **Gradio** `ChatInterface`, `launch(share=True)` | Gives the shareable link Task #11 requires. |
| Secrets | `.env` (git-ignored) with `OPENROUTER_API_KEY`, loaded by `python-dotenv`. `.env.example` is committed with a placeholder value | Keys are never committed. |

### Repo layout

See the README for the current layout. Code lives in the `creditcoach/` Python package, with one subpackage per area added as each task starts: `agent/` (prompt, orchestration, guardrails), `rag/` (corpus, ingestion, retrieval), `tools/` (MCP server and tools), `memory/` (goal store), and `app/` (Gradio UI). Data, evals, and docs sit at the repo root.

## 3. Kickoff Review: Key Takeaways from requirements.md

**Customer: Aravind.** Aravind is 22, in their first full-time job, and has had their first credit card for 8 months. Their score just dropped 20 points and they panicked. They're saving for a car and want plain-language answers grounded in their own account data, not generic blog advice. They also want a clear warning about "quick fixes" like payday loans and credit-repair services.

**What we're building:** an assistant that combines three things:
1. **RAG** over scoring-factor, financial-literacy, and product-risk content
2. **Tools** that read simulated score history and account data
3. **Memory** of the user's goal (target score, target date, purpose) across sessions

**Non-negotiable guardrails (§5):** these drive design choices from Week 1, not just Week 3.
1. Never guarantee a score outcome or timeline. Frame every projection as educational.
2. Never endorse predatory products (payday loans, guaranteed credit repair, advance-fee scams), and proactively flag them.
3. Never fabricate figures. Every score, balance, or factor must come from a live tool call.
4. Never silently override the user's stored goal.
5. Track tool-call failures and degrade gracefully ("here's what I last confirmed").

**Our acceptance bar:** the 6 sample queries in requirements.md §3. They become the eval suite in Task #27.

**What the sample data already shows (`sample_data/credit_profile_sample.xlsx`):**
- USR-001's score went from 690 (Jul 2026) to 670 (Aug, *utilization spike*) and then to 650 (Sep, *hard inquiry + utilization spike*). The Sep drop is exactly the "20 points this month" in sample query #1.
- Revolving accounts: credit card ACC-01 is at $1,180 / $1,500 = **79% utilization**, credit card ACC-02 is at $220 / $2,000 = 11%, and retail card ACC-05 is at $95 / $500 = 19%. Overall revolving utilization is $1,495 / $4,000 = **37.4%**.
- Installment loans (no limit, so not part of utilization): student loan ACC-03 has an $8,400 balance and auto loan ACC-04 has a $6,100 balance.
- `credit_score_factors_guide.pdf` explains both causes: a utilization spike above 30% typically costs 10 to 40 points, and a hard inquiry costs 2 to 10. It also covers payday loans and credit-repair red flags. This makes it the seed document for the RAG corpus (Task #7).

## 4. Working Agreements

- **Definition of Done** comes from the `tasks.md` column. A task is not done until its *Evidence of Completion* artifact is in the repo.
- Evidence (logs, transcripts, screenshots) goes in `docs/evidence/week-N/`.
- A task moves forward only after the team signs off on the previous task's evidence.
- All guidance the product gives is educational. No real financial advice, loan origination, or credit repair (requirements.md §4).

## 5. Sign-off: "I have read requirements.md"

Each member checks their box and adds the date.

| Member | Role | Read requirements.md | Agree to stack | Date |
|---|---|---|---|---|
| Aman | All roles (shared) | [ ] | [ ] | |
| Anik | All roles (shared) | [ ] | [ ] | |
| Sudip | All roles (shared) | [ ] | [ ] | |
