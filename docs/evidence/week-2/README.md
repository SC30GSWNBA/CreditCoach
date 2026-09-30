# Week 2 Evidence and Status

Each task is **Done** only when its *Evidence of Completion* from [tasks.md](../../../tasks.md) is in the repo and the team has signed off.

| # | Task | Deliverable | Evidence | Built | Team sign-off |
|---|---|---|---|---|---|
| 12 | Tool specs | [docs/tools.md](../../tools.md) | Both signatures with inputs, outputs, error cases, example input/output, and 15 test cases for Tasks 13–14 | ✅ | ⬜ Each member ticks their row in tools.md §7 and answers the §6 open questions |
| 13 | Score-history tool | [creditcoach/tools/score_history.py](../../../creditcoach/tools/score_history.py) | [task-13-score-history-test.md](task-13-score-history-test.md): known periods and invalid periods logged, 6/6 correct; 42 pytest tests pass | ✅ | ⬜ Review the test log |
| 14 | Account-summary tool | [creditcoach/tools/account_summary.py](../../../creditcoach/tools/account_summary.py) | [task-14-account-summary-test.md](task-14-account-summary-test.md): known users and an unknown user logged, 6/6 correct; 28 pytest tests pass | ✅ | ⬜ Review the test log |
| 15 | MCP round trip | [creditcoach/tools/server.py](../../../creditcoach/tools/server.py), [creditcoach/agent/mcp_host.py](../../../creditcoach/agent/mcp_host.py), [pipeline.py](../../../creditcoach/agent/pipeline.py) | [task-15-mcp-round-trip.md](task-15-mcp-round-trip.md): one live query, both tools called over MCP, 6/6 key figures traced to tool output; 19 offline MCP tests | ✅ | ⬜ Review the trace |
| 16 | Memory schema | | | ⬜ | ⬜ |
| 17 | Goal recall across 2 sessions | | | ⬜ | ⬜ |
| 18 | Agent trace panel in the UI | | | ⬜ | ⬜ |

## Week 2 demo goal

> *The same Gradio UI now pulls live score-factor and account data, and remembers the user's target-score goal across two visits; visible live in the chat.* (tasks.md)
