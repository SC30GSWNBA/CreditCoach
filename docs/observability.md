# CreditCoach: Observability

*Week 4 · Task #26 (tracing), #31 (dashboard) · Last updated: 2026-11-01 (the dashboard's Cost and speed view) · Status: Draft for team review · Code: `creditcoach/observability.py`*

Until Week 3, what happened inside an answer was spread across several places: the agent trace in the chat, one JSON log line per tool call, the guardrail log, the cache log, and the record each reply leaves in Neon. None of them carried an ID linking the lines for one question. Since Task #26, every question is one **OpenTelemetry trace**, and every step of it is a span in that trace, so retrievals, tool calls, guardrail triggers, tool failures, model calls and cache lookups for one request all share a single trace ID. The same traces feed the Task #31 dashboard and the Task #29 error analysis.

## 1. What is recorded

`agent.pipeline.answer` opens one root span per question; everything below is a child of it.

| Span | What it records | Events on it |
|---|---|---|
| `creditcoach.answer` | user, memory session, the (masked) question, the answer, model, guardrail action, cache status, tool calls and failures, total seconds | an answer-cache `skip`, if the answer may not be stored; `clarify.reference` when the question points at a loan nobody has named (Task 32) |
| `guardrail.input` | the input rails: rules found, predatory products named | `guardrail.trigger` per finding (S1–S3, S5, G2) |
| `memory.context` | building the MEMORY section (only with a memory session) | |
| `cache.answer` | the answer-cache lookup: hit, miss or stale, and how it matched | `cache` per lookup |
| `retrieval` | passage ids, categories and scores; whether the product-risk passages were added; the searches drawn from the user's own data (`retrieval.data_probes`, Task 30) | `cache` per lookup; `retrieval.empty` if nothing matched; `retrieval.failed` if the library couldn't be searched and the answer went on without it (Task 32) |
| `memory.recall` | the stored goal and how many earlier sessions there are | |
| `context.build` | loading the user's profile and building the prompt (data backend, history length) | |
| `agent` | the tool-calling loop | `tool.server_unavailable` if the tool server couldn't start (Task 32) |
| `tool.<name>` | arguments, ok, error code, attempts, cached, milliseconds, the result (with `last_confirmed` when a failed call fell back to it, Task 32). A failed call has **ERROR** status | `cache`; `tool.retry`; `tool.failure` with the code and message |
| `llm.chat` | model asked for and model that answered, tokens in and out, cost in US dollars, the messages and the reply | `llm.fallback` when the fallback model answered |
| `guardrail.output` | passed, reframed or blocked; whether the model review ran; rules found and still failing | `guardrail.trigger` per finding (G1–G3, S2, S4, S5) |

The trace ID is also saved on every reply's record in Neon (`trace_id` in the `assistant_message` event), is on `Answer.trace_id`, is printed by the command-line transcript, and is in every `tool_call` log line. Any of them leads to the full trace.

## 2. Where traces go

| Destination | When | How to read it |
|---|---|---|
| Local files: `.traces/<UTC date>.jsonl`, one JSON line per span (git-ignored) | Always, unless `CREDITCOACH_TRACES=off` | `observability.load("<trace id>")` returns one request's spans |
| **Langfuse** over OTLP | When `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set in `.env` (`LANGFUSE_HOST` for another region or a self-hosted server) | The Langfuse UI: model calls show as generations with tokens and cost, tool calls as tool observations, and the user and session are filled in |
| Any other OpenTelemetry collector | Without Langfuse keys, when `OTEL_EXPORTER_OTLP_ENDPOINT` is set | That tool's UI |

Checked live on 2026-10-25 against the team's Langfuse Cloud project (Japan region, `LANGFUSE_HOST=https://jp.cloud.langfuse.com`): every span arrives with its Langfuse type (guardrail, retriever, agent, tool, generation), the user and memory session on every span, inputs and outputs, and for model calls the model, tokens and cost, which Langfuse matches to its own price table.

**Reading traces back from Langfuse** (for the Task #31 dashboard): use `GET /api/public/v2/observations` (filter by `traceId`, or by `fromStartTime` and `toStartTime`; add `fields=core,basic,usage,model,io` for more than the core fields). The older `/api/public/traces` and `/api/public/observations` already return 410 on Langfuse Cloud and are removed on 2026-11-16. Sending traces is not affected: it goes over OpenTelemetry.

Every trace carries `deployment.environment` (`CREDITCOACH_ENV`, default `local`; the Docker image sets `railway`), so traces from the deployed build can be told apart from local runs.

**On Railway, Langfuse is the record.** The container's own disk is replaced on every redeploy, so its `.traces/` files are lost with it. Testers' traces are kept only in Langfuse, which is where the Task #29 error analysis read them and where the Task #31 dashboard reads them (it falls back to `.traces/` only when Langfuse can't be reached). Checked live on 2026-10-28: two questions asked on Railway as USR-019 arrived as two complete traces tagged `railway` (13 spans each, both tools, the guardrail checks), and the dashboard counts them under real use. Before that, the only `railway` span was a sign-in's memory consolidation: nobody had asked a question there since `LANGFUSE_HOST` was set.

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

Since Task #29 testers can rate an answer in the chat. A 👍 or 👎 is attached to that answer's trace as the score `user.feedback` (true or false, with the verdict as its comment), and a 👎's reason as `user.feedback.reason` (*Wrong or missing figure*, *Didn't answer my question*, *Too slow*, *Hard to follow*). In Langfuse, filter traces by those scores to read every rated answer with everything that went into it ([task-29-error-analysis.md](evidence/week-4/task-29-error-analysis.md)).

Since Task #31 the chat UI has a **Dashboard** tab for every signed-in user (team's logins only until 2026-10-29; `creditcoach/app/dashboard.py`): the tool-call failure rate, guardrail trigger count and goal-recall accuracy, read from Langfuse with the v2 observations API above (else from `.traces/`), with real use kept apart from eval and test runs ([task-31-dashboard.md](evidence/week-4/task-31-dashboard.md)). A cold read from Langfuse takes several seconds (about 7 s for a week of traces), so the tab is shown first, with a loading note, and filled in after; the loaded traces are kept for 60 s.

**Cost and speed (2026-11-01).** The Dashboard tab has two views: **Quality** (the three measures above) and **Cost and speed**, for the same period and traffic ([cost-speed-and-counters.md](evidence/week-4/cost-speed-and-counters.md)). It reads three more span names, `llm.chat`, `agent` and `retrieval`, with each span's id, parent and duration (Langfuse gives them as `id`, `parentObservationId` and `latency` in seconds). An answer's cost is the sum of its model calls' `gen_ai.usage.cost`, and the span a call sits under says what it was:

| A `llm.chat` span under | Is | Counted as |
|---|---|---|
| `agent` | the answer model writing the answer | Answer model |
| `guardrail.output`, calling `SMALL_MODEL` | the output check | Output check |
| `guardrail.output`, calling any other model | the rewrite of a reframed answer | Rewrites (spend goes to the answer model's bar) |
| anything else (an `eval.judge`) | not part of the answer | left out |

The view shows spend, cost per answer (and its p95), response time (p50 and p95, from the `creditcoach.answer` span), tokens and cost per 1M tokens; cost against response time for every answer (up to the newest 3,000), each model's median marked; each answer model compared; spend, response time and tokens by day; and the average seconds and the spend per pipeline step (answer model, tools, output check, rewrites, retrieval, input check, other). Percentiles are by nearest rank, as the eval reports give them. It also shows the 50-case eval runs per model as cost against speed and quality (passed, median, 90% within, cost per answer, against the 15 s target). The Docker image leaves `docs/` out, so those figures ship as `creditcoach/evals/model_comparison.json`, written by `scripts/model_comparison.py` from the runs and their traces.

**Every trace says which process made it (2026-10-29).** A new trace is tagged by its process: the chat app calls `observability.set_run("app")` at startup; any other process tags its traces `script` and `script:<name>` (for example `script:task32_edge_cases`, or `script:evals` for the harness), and the eval harness's own `eval` and `eval:<label>` tags take their place on its cases. The dashboard counts as real use only `app`-tagged traces (and, from before the tag, the Railway build's); everything else is an eval or test run, listed by run. Before this, only `eval`-tagged traces were kept apart, so the evidence and benchmark scripts' answers (Task 30's repeat batches, Task 32's edge cases, the cache benchmark) were counted as real use, and "Eval runs" showed nothing after 27 Oct, the last harness run. Older untagged local traces are listed as "local, untagged": none of them came from the chat app, whose answers have carried a session ID since Task #26 (the 146 from 25–29 Oct are evals and evidence scripts). Since 2026-10-30, "Real use" says how many answers in the period are under eval and test runs, so a short count isn't read as lost data. Langfuse cuts long metadata strings, so a stored goal's JSON can arrive incomplete; the dashboard reads its target and session from the cut text.

The trace made one cost visible straight away: `context.build` takes about 1.3 s, almost all of it loading the user's profile from Neon on every question. That is a lead for the Task #29 error analysis.

## 5. Open questions for team review

1. **Langfuse Cloud or self-hosted.** Cloud's free tier is enough for testers and the demo, and needs only the two keys. Self-hosting means one more service to run on Railway. Proposal: Langfuse Cloud, with one project shared by the team.
2. **What leaves the machine.** With Langfuse on, model inputs (the profile, passages, tool results) and answers go to Langfuse. The data is synthetic and identifiers are masked, but testers' sign-up answers shape their profiles. Proposal: send everything while testing, and revisit before anyone outside the course uses it.
3. **Keeping local traces.** `.traces/` grows by a file a day and nothing deletes old ones. Proposal: keep 14 days. The Task #31 dashboard reads Langfuse first and the local files only as a fallback, so no clean-up was added with it; this is still open.

## 6. Sign-off

| Member | Reviewed | Date |
|---|---|---|
| Aman | [ ] | |
| Anil | [ ] | |
| Sudip | [ ] | |
