# Task 26 Evidence: One Request, One Trace

*2026-10-25 · Code: `creditcoach/observability.py`, wired into `creditcoach/agent/pipeline.py`, `creditcoach/agent/mcp_host.py`, `creditcoach/llm.py`, `creditcoach/guardrails/rails.py`, `creditcoach/cache/__init__.py` · Tests: `tests/test_observability.py` · Script: `uv run python scripts/task26_trace_export.py`*

**Definition of Done:** every event for one request shares a single trace ID.

**Result: ✅ PASS**

Trace ID: **`055838a4632f82be0aab02dc2d81d795`** · exported trace: [runs/task-26-trace.json](runs/task-26-trace.json) (13 spans, 16 events)

The request: *"Should I take out this payday loan to pay off my credit card?"*, asked as USR-001 with an open memory session, the cache on and the guardrail layer on, as the chat UI asks it. `get_account_summary` was made to time out through the MCP host's real timeout path, so one request carries both a successful tool call and a failed one. Every span was recorded with OpenTelemetry and written to `.traces/` as the app writes it, and sent to Langfuse.

## Checks

| Check | Result |
|---|---|
| Every span emitted during the run belongs to trace `055838a4…` | ✅ 13 of 13 spans |
| The exported file holds all of them | ✅ 13 spans |
| One root span (`creditcoach.answer`); every other span hangs under it | ✅ 1 root |
| Retrieval: `retrieval` span with the passages and scores | ✅ |
| Tool call: `tool.<name>` span, OK status | ✅ |
| Guardrail trigger: `guardrail.trigger` event with the rule | ✅ |
| Tool failure: `tool.<name>` span with ERROR status and a `tool.failure` event | ✅ |

Also in the same trace:

- ✅ Model call: `llm.chat` span: model, tokens, cost
- ✅ Cache lookup: `cache` event on the span that looked
- ✅ Memory recall: `memory.recall` span: stored goal, earlier sessions

## Span tree

Each line is one span: when it started after the request began, how long it took, its status, and the attributes that matter most. The full attributes are in the exported JSON.

```
creditcoach.answer  [+0 ms, 15,000 ms] · 1 event · id=USR-001, guardrail=passed, cache=miss, tool_failures=1
    guardrail.input  [+0 ms, 82 ms] · 1 event · rules=['G2'], products=['payday loan']
    memory.context  [+82 ms, 0 ms]
    cache.answer  [+82 ms, 8 ms] · 3 events · result=miss
    retrieval  [+91 ms, 45 ms] · 6 events · passages=['payday-loans-and-instant-loan-apps#02', 'minimum-due-and-interest#02', 'payday-loans-and-instant-loan-apps#03']
    memory.recall  [+136 ms, 0 ms] · sessions=0
    context.build  [+136 ms, 1,505 ms]
    agent  [+1,643 ms, 11,853 ms]
        tool.get_score_history  [+2,055 ms, 1,167 ms] · 2 events · ok=True, attempts=1, cached=False
        tool.get_account_summary  [+3,223 ms, 1 ms] **ERROR** · 3 events · ok=False, code=DATA_UNAVAILABLE, attempts=2, cached=False
        llm.chat  [+3,238 ms, 10,168 ms] · response.model=openai/gpt-5, usage.input_tokens=4687, usage.output_tokens=1058, usage.cost=0.01125475
    guardrail.output  [+13,496 ms, 1,503 ms] · action=passed, reviewed=True
        llm.chat  [+13,511 ms, 1,473 ms] · response.model=openai/gpt-5-mini, usage.input_tokens=895, usage.output_tokens=39, usage.cost=0.00030175
```

## Event timeline

Every event in the trace, in order, with the span it belongs to. All carry the same trace ID.

| # | Event | Span | Detail |
|---|---|---|---|
| 1 | `guardrail.trigger` | `guardrail.input` | G2 at input: the question mentions a predatory product ['payday loan'] |
| 2 | `cache` | `cache.answer` | embedding: miss |
| 3 | `cache` | `cache.answer` | embedding: store |
| 4 | `cache` | `cache.answer` | answer: miss (nothing stored for this user) |
| 5 | `cache` | `retrieval` | retrieval: miss |
| 6 | `cache` | `retrieval` | embedding: hit |
| 7 | `cache` | `retrieval` | retrieval: store |
| 8 | `cache` | `retrieval` | retrieval: miss |
| 9 | `cache` | `retrieval` | embedding: hit |
| 10 | `cache` | `retrieval` | retrieval: store |
| 11 | `cache` | `tool.get_score_history` | tool: miss |
| 12 | `cache` | `tool.get_score_history` | tool: store |
| 13 | `cache` | `tool.get_account_summary` | tool: miss |
| 14 | `tool.retry` | `tool.get_account_summary` | DATA_UNAVAILABLE: retrying once |
| 15 | `tool.failure` | `tool.get_account_summary` | get_account_summary DATA_UNAVAILABLE: get_account_summary took longer than 1e-06 seconds. |
| 16 | `cache` | `creditcoach.answer` | answer: skip (a tool call failed) |

## What the request did

- Spans by kind: guardrail.input 1, memory.context 1, cache.answer 1, retrieval 1, memory.recall 1, context.build 1, tool.* 2, llm.chat 2, agent 1, guardrail.output 1, creditcoach.answer 1
- Model calls: 2, together $0.0116 (openai/gpt-5, openai/gpt-5-mini)
- Guardrail: passed · answer cache: miss · tool failures: 1 · 14.92 s in all

The answer the user saw:

> Short answer: I don’t recommend a payday/instant loan to pay a credit card. It’s a high‑risk product. It usually swaps card interest for an even higher cost, adds a new debt, and can lead to collections if the short deadline is missed [1], [2].
>
> Where you stand:
> - Your latest score is 650 (Sep 2026), down from 690 in July (690 → 650, -40). The recent drops were mainly from a utilization spike and a hard inquiry.
> - Taking a payday-style loan could add cost and risk without fixing the root issue (high card utilization). It may also mean another hard inquiry, which can weigh on your score.
>
> Safer moves you can take now:
> - Pay at least the minimum due, and as much above it as you can; pause new spends on the card until the balance is under control [2].
> - Call your card issuer and ask about converting the outstanding into EMIs. This usually costs less than revolving at card interest; check the interest rate and any processing fee before you agree [2].
> - If repayments still feel tight, ask your bank for a payment plan or free credit counselling (many banks run financial literacy and counselling centres). A balance transfer to a regulated bank card can sometimes lower cost if you qualify—compare total fees and rates first.
>
> Notes on digital lending in India (general info): genuine digital loans must be from an RBI‑regulated bank/NBFC and come with a Key Fact Statement showing the all‑in APR. Apps should not demand your contacts/photos, and there’s a cooling‑off period [3]. Even so, payday‑style loans are typically a bad trade for card debt [1].
>
> I couldn’t pull your account details just now (balances/limits/utilization). If you’d like, ask me to refresh, and I’ll use your actual figures to pick which card to pay down first and by how much.

