# Week 2 Evidence and Status

Each task is **Done** only when its *Evidence of Completion* from [tasks.md](../../../tasks.md) is in the repo and the team has signed off.

| # | Task | Deliverable | Evidence | Built | Team sign-off |
|---|---|---|---|---|---|
| 12 | Tool specs | [docs/tools.md](../../tools.md) | Both signatures with inputs, outputs, error cases, example input/output, and 15 test cases for Tasks 13–14 | ✅ | ✅ Sudip: Reviewed and Signed Off (2026-10-02) in tools.md §7 · ⬜ Aman and Anil tick their rows; the team answers the §6 open questions |
| 13 | Score-history tool | [creditcoach/tools/score_history.py](../../../creditcoach/tools/score_history.py) | [task-13-score-history-test.md](task-13-score-history-test.md): known periods and invalid periods logged, 6/6 correct; all 75 score-history figures the 50 requirements.md queries rely on match; 42 pytest tests pass | ✅ | ✅ Sudip: Reviewed and Signed Off (2026-10-02) · ⬜ Aman and Anil review the test log |
| 14 | Account-summary tool | [creditcoach/tools/account_summary.py](../../../creditcoach/tools/account_summary.py) | [task-14-account-summary-test.md](task-14-account-summary-test.md): known users and an unknown user logged, 6/6 correct; all 71 account figures the 50 requirements.md queries rely on match; 28 pytest tests pass | ✅ | ✅ Sudip: Reviewed and Signed Off (2026-10-02) · ⬜ Aman and Anil review the test log |
| 15 | MCP round trip | [creditcoach/tools/server.py](../../../creditcoach/tools/server.py), [creditcoach/agent/mcp_host.py](../../../creditcoach/agent/mcp_host.py), [pipeline.py](../../../creditcoach/agent/pipeline.py) | [task-15-mcp-round-trip.md](task-15-mcp-round-trip.md): one live query, both tools called over MCP, 6/6 key figures traced to tool output; 21 offline MCP tests. [task-15-all-queries.md](task-15-all-queries.md): all 50 requirements.md queries live over MCP, each as its own user: 32 pass, 12 pass with memory or multi-turn parts deferred, 6 fail (5 missing an expected behavior, 1 using "definitely"), 0 crashes, after the 2026-10-02 fixes (both tools prefetched over MCP, prompt rules on figures, a worked example that matches no user). Before the fixes: 29 pass, 9 deferred, 12 fail ([saved run](runs/task-15-all-queries-before-fixes.json)); the first run had 25 pass, 16 fail | ✅ | ✅ Sudip: Reviewed and Signed Off (2026-10-02) · ⬜ Aman and Anil review the trace |
| 16 | Memory schema | [docs/memory.md](../../memory.md), [creditcoach/memory/](../../../creditcoach/memory/) | [task-16-memory-record.md](task-16-memory-record.md): goal record written in one session and read back in another, all fields match; a change keeps the previous goal; invalid goals refused; a live dream consolidates 3 sessions without touching the goal or storing a figure; 40 pytest tests | ✅ | ✅ Sudip: Reviewed and Signed Off (2026-10-02) in memory.md §10 · ⬜ Aman and Anil tick their rows; the team answers the §9 open questions |
| 17 | Goal recall across 2 sessions | [creditcoach/memory/recall.py](../../../creditcoach/memory/recall.py), [pipeline.py](../../../creditcoach/agent/pipeline.py), [system_prompt.md](../../../creditcoach/prompts/system_prompt.md) | [task-17-goal-recall.md](task-17-goal-recall.md): live, through the chat UI's functions: Aravind's goal (§3 #5) and Manish's (§4 #35) saved in session 1 and recalled, unprompted, in session 2 (§4 #37, #36); goal read back exactly (#39), not changed by "should I aim for 800?" (#40), updated to 750 keeping date and purpose (#38); 18/18 checks; 20 pytest tests | ✅ | ✅ Sudip: Reviewed and Signed Off (2026-10-02) · ⬜ Aman and Anil review the transcripts |
| 18 | Agent trace panel in the UI | [creditcoach/app/trace.py](../../../creditcoach/app/trace.py), [main.py](../../../creditcoach/app/main.py) | [task-18-agent-trace.md](task-18-agent-trace.md): screenshots on a real query: live progress while waiting (steps, timers, rotating credit tips), then an expandable trace listing both tool calls with results and the recalled goal; 18 pytest tests | ✅ | ✅ Sudip: Reviewed and Signed Off (2026-10-02) · ⬜ Aman and Anil review the screenshots |

## Week 2 demo goal

> *The same Gradio UI now pulls live score-factor and account data, and remembers the user's target-score goal across two visits; visible live in the chat.* (tasks.md)

| Part of the goal | Status | Evidence |
|---|---|---|
| Live score-factor and account data in the chat | ✅ | Both tools called over MCP for the signed-in user ([Task 15](task-15-mcp-round-trip.md)) |
| Remembers the target-score goal across two visits | ✅ | Goal saved in session 1 and recalled, unprompted, in session 2 ([Task 17](task-17-goal-recall.md)) |
| Visible live in the chat | ✅ | Live progress while waiting, then an expandable agent trace with each tool call and the recalled goal ([Task 18](task-18-agent-trace.md)) |
| Team sign-off | ✅ Sudip, ⬜ Aman and Anil | Sign-off column above |

**Additional (outside the task plan):**
- Full conversation memory (Task 16 goes beyond the goal record): every sign-in, question, answer, goal change and sign-out is saved per user as append-only episodes, and "dreaming" (our own version of Anthropic's technique) consolidates past sessions into facts, preferences and summaries, with validators that reject credit figures and words the user never said. See [docs/memory.md](../../memory.md).
- Memory shared through git: `memory/` is committed, `scripts/memory_sync.py` turns local chat sessions into a pull request, and `memory_sync.py pull` fetches everyone's, so any teammate can continue a user's history. See [README > Memory](../../../README.md#memory).
- Live progress while waiting (Task 18): each step with a timer, plus rotating credit tips during the slowest step, because an answer takes about 18 s with GPT-5 (measured in Task 18).
- All-50-query evaluation (2026-10-02): see below.

## Evaluation on all 50 requirements.md queries (2026-10-02)

Tasks 12–15 were first evaluated on hand-picked cases built around the 6 sample queries. They now also run all 50 requirements.md queries from the golden set in `creditcoach/evals/` (see [README > Evaluation queries](../../../README.md#evaluation-queries)):

- **Tools (Tasks 12–14):** every figure the 50 expected answers rely on (146 values) matches the tools, checked on every pull request by `tests/test_golden_queries.py`.
- **Agent over MCP (Task 15):** three runs over all 50 queries on 2026-10-02:

  | Run | Pass | Partly deferred | Fail |
  |---|---|---|---|
  | First run (Task 15 prompt) | 25 | 9 | 16 |
  | Task 17 prompt ([saved](runs/task-15-all-queries-before-fixes.json)) | 29 | 9 | 12 |
  | After the fixes below ([current](runs/task-15-all-queries.json)) | **32** | **12** | **6** |

  The main finding of the earlier runs was that **for plan, product and goal questions the model answered without calling the tools** (#3, #26, #27, #29, #32, #34, #44), so answers were generic and missed the user's own figures. Three fixes followed:
  1. **Prefetch:** the host now fetches the last 12 months of score history and the account summary over MCP before the model's first turn ([docs/tools.md](../../tools.md) §4).
  2. **Prompt rules:** plans state the current score and the figure they turn on, trends give the start and end score, and a high-risk account is always named.
  3. **Content:** the worked utilization example in the prompt and `corpus/03` used Aravind's real figures (₹74,750 ÷ ₹2,00,000), which #45 repeated as his utilization when the account tool timed out; it now matches no user, and a test guards it. Topics the library doesn't cover (#48, buy now, pay later) get "I don't have specific information on that".

  All ten targeted failures now pass (#3, #25, #26, #27, #29, #32, #34, #44, #45, #48), and no query answers without the user's data. **Still failing:** #11 omits the typical 60–110 point range for a late payment (retrieval doesn't return that passage; switching to the fusion strategy is the candidate fix), #12 doesn't point to free credit counselling, #18 and #21 leave out the 30% guide or a payment plan, #28 doesn't ask about a goal, and #9 uses "definitely" for a utilization target. #18, #21, #28 and #9 passed in the run before, so they vary between runs; Task 27 should run each query more than once. **Cost:** answers are about a third longer (median 1,160 → 1,540 characters) and median model time rose from 11.8 s to 15.4 s; the prompt rules, not the prefetch (about 0.1 s), account for it. These are inputs for the Task 29 error analysis.
- **Goal memory (#3, #5, #23, #25, #35–#40):** the 50-query run starts with empty memory, so these are marked "partly deferred" there. Since Task 17 they are checked live with a stored goal and an earlier session in [task-17-goal-recall.md](task-17-goal-recall.md) (#5, #35–#40, all pass). The Task 27 harness will seed memory for all of them. Multi-turn follow-ups (#47) wait for Task 32.
