# CreditCoach: Observability

*Week 4 · Task #26 · Last updated: 2026-10-25 · Status: Draft for team review · Code: `creditcoach/observability.py`*

Until Week 3, what happened inside an answer was spread across several places: the agent trace in the chat, one JSON log line per tool call, the guardrail log, the cache log, and the record each reply leaves in Neon. None of them carried an ID linking the lines for one question. Since Task #26, every question is one **OpenTelemetry trace**, and every step of it is a span in that trace, so retrievals, tool calls, guardrail triggers, tool failures, model calls and cache lookups for one request all share a single trace ID. The same traces feed the Task #31 dashboard and the Task #29 error analysis.

## 1. What is recorded

`agent.pipeline.answer` opens one root span per question; everything below is a child of it.

| Span | What it records | Events on it |
|---|---|---|
| `creditcoach.answer` | user, memory session, the (masked) question, the answer, model, guardrail action, cache status, tool calls and failures, total seconds | an answer-cache `skip`, if the answer may not be stored |
| `guardrail.input` | the input rails: rules found, predatory products named | `guardrail.trigger` per finding (S1–S3, G2) |
| `memory.context` | building the MEMORY section (only with a memory session) | |
| `cache.answer` | the answer-cache lookup: hit, miss or stale, and how it matched | `cache` per lookup |
| `retrieval` | passage ids, categories and scores; whether the product-risk passages were added | `cache` per lookup; `retrieval.empty` if nothing matched |
| `memory.recall` | the stored goal and how many earlier sessions there are | |
| `context.build` | loading the user's profile and building the prompt (data backend, history length) | |
| `agent` | the tool-calling loop | |
| `tool.<name>` | arguments, ok, error code, attempts, cached, milliseconds, the result. A failed call has **ERROR** status | `cache`; `tool.retry`; `tool.failure` with the code and message |
| `llm.chat` | model asked for and model that answered, tokens in and out, cost in US dollars, the messages and the reply | `llm.fallback` when the fallback model answered |
| `guardrail.output` | passed, reframed or blocked; whether the model review ran; rules found and still failing | `guardrail.trigger` per finding (G1–G3, S2, S4) |

The trace ID is also saved on every reply's record in Neon (`trace_id` in the `assistant_message` event), is on `Answer.trace_id`, is printed by the command-line transcript, and is in every `tool_call` log line. Any of them leads to the full trace.

## 2. Where traces go

| Destination | When | How to read it |
|---|---|---|
| Local files: `.traces/<UTC date>.jsonl`, one JSON line per span (git-ignored) | Always, unless `CREDITCOACH_TRACES=off` | `observability.load("<trace id>")` returns one request's spans |
| **Langfuse** over OTLP | When `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set in `.env` (`LANGFUSE_HOST` for another region or a self-hosted server) | The Langfuse UI: model calls show as generations with tokens and cost, tool calls as tool observations, and the user and session are filled in |
| Any other OpenTelemetry collector | Without Langfuse keys, when `OTEL_EXPORTER_OTLP_ENDPOINT` is set | That tool's UI |

Checked live on 2026-10-25 against the team's Langfuse Cloud project (Japan region, `LANGFUSE_HOST=https://jp.cloud.langfuse.com`): every span arrives with its Langfuse type (guardrail, retriever, agent, tool, generation), the user and memory session on every span, inputs and outputs, and for model calls the model, tokens and cost, which Langfuse matches to its own price table.

**Reading traces back from Langfuse** (for the Task #31 dashboard): use `GET /api/public/v2/observations` (filter by `traceId`, or by `fromStartTime` and `toStartTime`; add `fields=core,basic,usage,model,io` for more than the core fields). The older `/api/public/traces` and `/api/public/observations` already return 410 on Langfuse Cloud and are removed on 2026-11-16. Sending traces is not affected: it goes over OpenTelemetry.

Every trace carries `deployment.environment` (`CREDITCOACH_ENV`, default `local`), so traces from the deployed build can be told apart from local runs.

**Why OpenTelemetry with Langfuse on top.** The implementation plan named both OpenTelemetry and Langfuse. Instrumenting with OpenTelemetry keeps the code free of any one vendor, and Langfuse accepts OpenTelemetry directly, so we get its LLM views (generations, cost, sessions) without its SDK. The local file means a fresh clone records traces with no account, and the Task #27 to #30 eval runs can be analysed offline.

## 3. Rules

1. **Recording never breaks an answer.** Exporter errors are logged and dropped. Recording outside a trace does nothing.
2. **No personal identifiers.** The question is recorded only after the input rails have masked PANs, card numbers and the like (rule S3); a test checks that a PAN never reaches a span.
3. **Text is capped** at 8,000 characters per attribute (`MAX_TEXT`), so a long prompt can't blow up a span.
4. **CreditCoach's spans only.** We keep our own tracer provider instead of the global one, so Chroma and NeMo Guardrails, which also use OpenTelemetry, don't mix their spans into ours.
5. **Tests never export.** `tests/conftest.py` sends spans to memory, so no test writes `.traces/` or reaches Langfuse.

## 4. Evidence

[task-26-trace.md](evidence/week-4/task-26-trace.md), live: the payday-loan question as USR-001 with `get_account_summary` forced to time out. 13 spans and 16 events, all under one trace ID, with a span tree and an event timeline: retrieval (with the product-risk passages), a successful `get_score_history`, the failed `get_account_summary` (ERROR, retried once, `DATA_UNAVAILABLE`), the G2 guardrail trigger, both model calls with tokens and cost, and every cache lookup. The exported trace is [runs/task-26-trace.json](evidence/week-4/runs/task-26-trace.json). `tests/test_observability.py` has 8 tests that need no API key.

Since Task #27 the eval harness runs each case inside an `eval.case` span, so the whole answer is under that case's trace (tagged `eval` and `eval:<label>`), and attaches the case's scores to the trace in Langfuse (`eval.pass`, `eval.expected`, `eval.judge.grounded`, `eval.judge.clear`) with `observability.score()`. A failing eval case opens straight onto the trace that explains it ([task-27-eval-harness.md](evidence/week-4/task-27-eval-harness.md)).

The trace made one cost visible straight away: `context.build` takes about 1.3 s, almost all of it loading the user's profile from Neon on every question. That is a lead for the Task #29 error analysis.

## 5. Open questions for team review

1. **Langfuse Cloud or self-hosted.** Cloud's free tier is enough for testers and the demo, and needs only the two keys. Self-hosting means one more service to run on Railway. Proposal: Langfuse Cloud, with one project shared by the team.
2. **What leaves the machine.** With Langfuse on, model inputs (the profile, passages, tool results) and answers go to Langfuse. The data is synthetic and identifiers are masked, but testers' sign-up answers shape their profiles. Proposal: send everything while testing, and revisit before anyone outside the course uses it.
3. **Keeping local traces.** `.traces/` grows by a file a day and nothing deletes old ones. Proposal: keep 14 days and add a clean-up when the dashboard (Task #31) reads them.

## 6. Sign-off

| Member | Reviewed | Date |
|---|---|---|
| Aman | [ ] | |
| Anil | [ ] | |
| Sudip | [ ] | |
