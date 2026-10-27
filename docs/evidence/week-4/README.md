# Week 4 Evidence and Status

Each task is **Done** only when its *Evidence of Completion* from [tasks.md](../../../tasks.md) is in the repo and the team has signed off.

| # | Task | Deliverable | Evidence | Built | Team sign-off |
|---|---|---|---|---|---|
| 26 | Observability | [creditcoach/observability.py](../../../creditcoach/observability.py) (OpenTelemetry tracing: local trace files, and Langfuse over OTLP when its keys are set), wired into [pipeline.py](../../../creditcoach/agent/pipeline.py), [mcp_host.py](../../../creditcoach/agent/mcp_host.py), [llm.py](../../../creditcoach/llm.py), the [guardrail layer](../../../creditcoach/guardrails/rails.py) and the [cache](../../../creditcoach/cache/__init__.py); design in [docs/observability.md](../../observability.md) | [task-26-trace.md](task-26-trace.md), live: one payday-loan question with `get_account_summary` forced to time out, exported as [runs/task-26-trace.json](runs/task-26-trace.json): **13 spans and 16 events under one trace ID**, with no span outside it. Shows retrieval with the product-risk passages, a successful tool call, the failed one (ERROR, retried once, `DATA_UNAVAILABLE`), the G2 guardrail trigger, both model calls with tokens and cost, and every cache lookup. The same trace was sent to the team's Langfuse Cloud project and checked there: every span arrived with its type, user, session, inputs and outputs, and model calls with tokens and cost. Also wired in: `creditcoach.check` reports where traces go and whether Langfuse accepts the keys. 8 pytest tests | ✅ | ⬜ Aman, Anil and Sudip review the trace and observability.md |
| 27 | Eval harness | [creditcoach/evals/harness.py](../../../creditcoach/evals/harness.py), run with `uv run python -m creditcoach.evals` (`--all` for all 50 queries, `--label` to name a run, `--rescore` to score a saved run again); the row checks shared with Task 24 in [sample_rows.py](../../../creditcoach/evals/sample_rows.py) | [task-27-eval-harness.md](task-27-eval-harness.md): the 6 expected-answers rows are 6 cases, each scored by **expected** (every separate thing the row asks for), an independent **judge** (`SMALL_MODEL`: meets the expected behavior, grounded, clear) and **run** (no crash, main model, not blocked). Each case is one trace with its scores attached in Langfuse, and has a slot for tester verdicts (Task 29). First live run: **6 of 6 pass** ([report](eval-task-27-first-run.md)). The `--all` path checked live on #26 and #45. 20 pytest tests | ✅ | ⬜ Aman, Anil and Sudip review the harness and the first run |
| 28 | Baseline eval run | [eval-baseline.md](eval-baseline.md): the baseline report (score, timestamp, per-case pass/fail), from `uv run python -m creditcoach.evals --all --label baseline`; data in [runs/eval-baseline.json](runs/eval-baseline.json) | [task-28-baseline.md](task-28-baseline.md): all 50 queries against the synthetic data (13 users), 2026-10-26 11:30: **36 of 50 pass (72%)**. Sample rows 4 of 6 (§3 #3 blocked by the G1 wording review; #5 follows from it), §4 32 of 44. Before it was recorded, a harness fix gave the §4 judge the user's profile (#24 was failed for details that are in it) and the saved answers were judged again (`--rejudge`); 6 verdicts changed between the two judgings, so the judge's own variation is noted for Tasks 29–30. 2 new pytest tests | ✅ | ⬜ Aman, Anil and Sudip review the baseline |
| 29 | Error analysis | | | ⬜ | ⬜ |
| 30 | Fixes and re-run | | | ⬜ | ⬜ |
| 31 | Dashboard | | | ⬜ | ⬜ |
| 32 | Edge cases | | | ⬜ | ⬜ |
| 33 | Demo script | | | ⬜ | ⬜ |
| 34 | Final rehearsal, deploy, backup video | Deployed early, for testers (2026-10-27): **https://creditcoach-production.up.railway.app**, built by Railway from the repo's [Dockerfile](../../../Dockerfile) on every merge to `main` (README, Deployment) | Rehearsal and backup video still to do. Deployment checked live: HTTP redirects to HTTPS, the welcome page loads in 0.6 s with every asset over HTTPS, sign-up asks for the invite code, signed-out visits go to the welcome page. Found and fixed while testing the image: the tool server never got `DATABASE_URL` without a `.env`, so every tool call failed (#56) | ⬜ (deploy done) | ⬜ |

## Week 4 demo goal

> *Full live walkthrough: Gradio UI + observability dashboard, an eval score shown before/after your error-analysis fixes, and a predatory-product refusal on demand.* (tasks.md)

| Part of the goal | Status | Evidence |
|---|---|---|
| Gradio UI | ✅ (Weeks 1–3) | [Week 3 tracker](../week-3/README.md) |
| Observability dashboard | ⬜ Traces recorded (Task 26); dashboard in Task 31 | [task-26-trace.md](task-26-trace.md) |
| Eval score before and after the error-analysis fixes | ⬜ Harness built (Task 27); baseline 36 of 50, 72% (Task 28); fixes and re-run in Tasks 29–30 | [task-27-eval-harness.md](task-27-eval-harness.md), [task-28-baseline.md](task-28-baseline.md) |
| Predatory-product refusal on demand | ✅ (Week 3) | [Task 21](../week-3/task-21-guardrail-tests.md), [Task 25](../week-3/task-25-badges.md) |
| Deployed build | ✅ (Railway, ahead of Task 34) | https://creditcoach-production.up.railway.app |
| Team sign-off | ⬜ | Sign-off column above |
