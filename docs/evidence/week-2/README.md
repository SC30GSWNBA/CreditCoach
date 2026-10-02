# Week 2 Evidence and Status

Each task is **Done** only when its *Evidence of Completion* from [tasks.md](../../../tasks.md) is in the repo and the team has signed off.

| # | Task | Deliverable | Evidence | Built | Team sign-off |
|---|---|---|---|---|---|
| 12 | Tool specs | [docs/tools.md](../../tools.md) | Both signatures with inputs, outputs, error cases, example input/output, and 15 test cases for Tasks 13–14 | ✅ | ⬜ Each member ticks their row in tools.md §7 and answers the §6 open questions |
| 13 | Score-history tool | [creditcoach/tools/score_history.py](../../../creditcoach/tools/score_history.py) | [task-13-score-history-test.md](task-13-score-history-test.md): known periods and invalid periods logged, 6/6 correct; all 75 score-history figures the 50 requirements.md queries rely on match; 42 pytest tests pass | ✅ | ⬜ Review the test log |
| 14 | Account-summary tool | [creditcoach/tools/account_summary.py](../../../creditcoach/tools/account_summary.py) | [task-14-account-summary-test.md](task-14-account-summary-test.md): known users and an unknown user logged, 6/6 correct; all 71 account figures the 50 requirements.md queries rely on match; 28 pytest tests pass | ✅ | ⬜ Review the test log |
| 15 | MCP round trip | [creditcoach/tools/server.py](../../../creditcoach/tools/server.py), [creditcoach/agent/mcp_host.py](../../../creditcoach/agent/mcp_host.py), [pipeline.py](../../../creditcoach/agent/pipeline.py) | [task-15-mcp-round-trip.md](task-15-mcp-round-trip.md): one live query, both tools called over MCP, 6/6 key figures traced to tool output; 19 offline MCP tests. [task-15-all-queries.md](task-15-all-queries.md): all 50 requirements.md queries live over MCP, each as its own user: 25 pass, 9 pass with memory or multi-turn parts deferred, 16 fail (10 where the model answered without calling a tool, 2 missing a figure, 4 missing an expected behavior), 0 crashes | ✅ | ⬜ Review the trace |
| 16 | Memory schema | | | ⬜ | ⬜ |
| 17 | Goal recall across 2 sessions | | | ⬜ | ⬜ |
| 18 | Agent trace panel in the UI | | | ⬜ | ⬜ |

## Week 2 demo goal

> *The same Gradio UI now pulls live score-factor and account data, and remembers the user's target-score goal across two visits; visible live in the chat.* (tasks.md)

## Evaluation on all 50 requirements.md queries (2026-10-02)

Tasks 12–15 were first evaluated on hand-picked cases built around the 6 sample queries. They now also run all 50 requirements.md queries from the golden set in `creditcoach/evals/` (see [README > Evaluation queries](../../../README.md#evaluation-queries)):

- **Tools (Tasks 12–14):** every figure the 50 expected answers rely on (146 values) matches the tools, checked on every pull request by `tests/test_golden_queries.py`.
- **Agent over MCP (Task 15):** the live run is the first baseline over all 50 queries, for Week 4. Its main finding: **for plan, product and goal questions the model often answers without calling the tools** (#3, #23–#27, #29, #32, #34, #44), so the answer is generic and misses the user's own figures. Smaller gaps: #15 leaves out the overall 37.4%, #12 reports the 12-month high (752) instead of the starting score (746), #11 omits the typical 60–110 point range, #28 doesn't ask about a goal, #30 doesn't say a dispute is free, and #48 describes buy-now-pay-later reporting practices that aren't in the corpus, which the expected answer forbids. These are inputs for the Task 29 error analysis, not fixed here.
- **Not testable yet:** goal memory and recall (#3, #5, #23, #25, #35–#40; Tasks 16–17) and multi-turn follow-ups (#47). These queries ran as single turns and are marked "partly deferred" until those tasks land.
