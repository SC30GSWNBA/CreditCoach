# Why CreditCoach answers with Claude Sonnet 5.5, and why it doesn't use prompt caching

*2026-11-01 · Decision made 2026-10-31 · Code: `creditcoach/config.py` (`CHAT_MODEL`)*

## Summary

CreditCoach's answer model is `anthropic/claude-sonnet-5.5`. At the sign-up cap of about 1,000 questions a month it costs about **$25 a month**. The next-best options would cost $11–$16.

We chose it anyway because of the brief for the latency bug: **bring answers to about 15 s without lowering answer quality.** Of the six models tested, Sonnet 5.5 is the only one that met both conditions:

- It matched GPT-5's eval score (43 of 50).
- It halved the response time: a median of 10.4 s against 20.4 s, and a 90th percentile of 14.9 s against 30.8 s.

Every cheaper model either passed fewer eval cases or missed the 15 s target. The extra cost is about $9–$14 a month.

We considered prompt caching to win back some of that cost and decided against it. Its default cache entry lasts **5 minutes**. At CreditCoach's traffic, most questions arrive more than 5 minutes after the one before, so the cache would rarely be read. Writing to the cache costs extra each time, so this saves roughly nothing. The 1-hour cache could save about $4–5 a month, but it would need Anthropic-specific code changes. It is the option to revisit if traffic grows (see [Prompt caching](#prompt-caching)).

## The constraint

The first persona test showed answers taking about 30 s, and one took 58 s ([persona-test-fixes.md](persona-test-fixes.md)). The brief was to:

1. Bring the response time to about 15 s.
2. Keep answer quality where it was. In practice, that means the 50-case eval score stays at GPT-5's **43/50** ([eval-effort-low.md](eval-effort-low.md), Task 30).

Cost was a factor to weigh, not a target. CreditCoach is a credit-education product, and a wrong or unhelpful answer about someone's credit costs more than a cent.

## What was tested

We tested in two stages:

1. **Speed screen.** We ran 8 questions through the full pipeline on six models, with guardrails on and the answer cache off.
2. **Full eval.** Models fast enough on the screen ran all 50 cases, with the same judge (GPT-5 mini) and the cache off.

Costs below are OpenRouter's reported cost for each call, from Langfuse. Each answer also includes about $0.0003 for the guardrail reviews.

| Model | Eval passed | Median | 90th pct | Over 15 s (of 50) | Cost per answer | Per month at 1,000 questions |
|---|---|---|---|---|---|---|
| GPT-5 (before) | 43/50 | 20.4 s | 30.8 s | 37 | $0.0107 | ~$11 |
| **Claude Sonnet 5.5 (chosen)** | **43/50** | **10.4 s** | **14.9 s** | **5** | $0.0250 | ~$25 |
| GPT-5.6 Terra | 39/50 | 6.8 s | 10.9 s | 1 | $0.0160 | ~$16 |
| Gemini 3.8 Flash | 41/50 | 9.7 s | 17.6 s | 10 | $0.0070 | ~$7 |
| Claude Haiku 5.5 | 36/50 | 9.2 s | 12.2 s | 2 | $0.0016 | ~$1.60 |
| GPT-5.6 Luna | speed screen only | 9.8 s* | 12.2 s* | n/a | n/a | n/a |

\* The speed screen ran only 8 questions, so Luna's figures are its median and slowest time on those 8, not a 90th percentile. Terra was faster on the same screen, so it was the GPT-5.6 model carried forward to the full eval.

Full reports: [Sonnet 5.5](eval-model-claude-sonnet-5-5.md), [GPT-5.6 Terra](eval-model-gpt-5-6-terra.md), [Gemini 3.8 Flash](eval-model-gemini-3-8-flash.md), [Haiku 5.5](eval-model-claude-haiku-5-5.md).

## Why not each alternative

### GPT-5, the previous model

- **Too slow.** 37 of the 50 eval answers took longer than 15 s. The 90th percentile was 30.8 s and the slowest answer 48.2 s. That was the bug being fixed.
- **Lowering its reasoning effort doesn't fix it.** Task 30 tried `REASONING_EFFORT=minimal`. It was 40% faster, but the score fell to 39/50.
- **Streaming the answer was not an option.** The output guardrails check the whole draft before the user sees any of it.
- **Cheapest of the high-scoring models**, at about $11 a month. That doesn't help if it can't meet the response-time target.

### GPT-5.6 Terra: fastest, mid-priced, but 4 fewer passing cases

Terra is the strongest alternative. It is the fastest model tested (6.8 s median, 10.9 s at the 90th percentile) and about $9 a month cheaper than Sonnet. We didn't choose it because it **passed 39 of 50 cases against 43**, and some of its failures are on core behaviour:

| Case | What Terra did |
|---|---|
| #16 "How much do I need to pay to get under 30%?" | Refused to use the user's own account data and gave no calculation. The guardrail layer then blocked the answer. This was the only "run" failure (a crash, the wrong model or a blocked answer) among the four models that ran the full eval |
| §3 #4 "Should I take out this payday loan…?", one of the six sample queries in requirements.md | Didn't clearly refuse to endorse the payday loan |
| #11 "Why did my score crash in April?" | Left out the typical impact of a late payment from the library (60 to 110 points) |
| #18 "What's my credit utilization?" | Didn't compare the user's utilization with the ~30% level |
| #25 "I only have 6 months now, not 12" | Didn't say that a 70-point rise in 6 months is ambitious |
| #28 "What should I focus on?" | Didn't ask whether the user has a goal to remember |

Terra writes much shorter answers: a median of **270 output tokens, against Sonnet's 745**. That accounts for much of its speed, and five of its six failures above are things it left out.

### Gemini 3.8 Flash: cheap, but misses the latency target

- **41/50**: two cases behind.
- **10 of 50 answers took longer than 15 s**, with a 90th percentile of 17.6 s. That misses the target.
- **One reliability problem.** It once rejected the guardrail rewrite request ("Requests ending with a model turn are not supported"). That answer then fell back to GPT-4o.

### Claude Haiku 5.5: by far the cheapest, but the weakest answers

- At about **$1.60 a month** it is the cheapest model tested, and it is fast (90th percentile 12.2 s).
- It passed **36/50**, seven cases fewer than GPT-5. That is too large a drop for an app whose job is to explain credit correctly.

### Claude Sonnet 5.5: the only option that met both conditions

- **Same score as GPT-5 (43/50).** It passed a different set of cases, though:
  - It passed #10, #12, #15, #28 and #44, which GPT-5 failed.
  - It failed #9, #20, #24, #25 and #35, which GPT-5 passed. Most of these were already flagged as unstable in Task 30.
  - Its #35 "failure" was actually correct: no goal tool was offered in that case. GPT-5 claimed it had saved the goal, which wasn't true. Sonnet said it couldn't save the goal.
- **Meets the latency target.** The 90th percentile is 14.9 s, and only 5 of 50 answers took longer than 15 s: guardrail rewrites and the two-session goal case.
- **Confirmed in live use:**
  - Persona 1's answers went from 30–58 s to 10–12 s.
  - Persona 2's median answer on the deployed build was 15.0 s.
  - The live red team re-run on Sonnet held on all 31 attacks and passed all 5 controls ([task-21-guardrail-tests.md](../week-3/task-21-guardrail-tests.md)).
- **Good refusals.** The new S5 rule declined questions about how CreditCoach is built in the first draft every time, with no rewrite needed.

## The cost, in context

| | Per month at 1,000 questions | Difference from Sonnet |
|---|---|---|
| Claude Sonnet 5.5 | ~$25 | n/a |
| GPT-5.6 Terra | ~$16 | −$9 |
| GPT-5 | ~$11 | −$14 |
| Gemini 3.8 Flash | ~$7 | −$18 |
| Claude Haiku 5.5 | ~$1.60 | −$23 |

**Why Sonnet costs more per answer.** Its per-token price ($2.48 per million, blended) is about the same as Terra's ($2.41). But it uses more tokens for the same prompt:
- **Input:** Claude's tokenizer counts our prompt as about 7,600 tokens, against about 4,900 for GPT-5 and 5,100 for Terra.
- **Output:** Sonnet writes fuller answers, a median of 745 output tokens.

**What the extra money buys.** Against Terra, the difference is 4 more passing cases out of 50, or 8% of answers. At 1,000 questions a month, that is about 80 more answers meeting the bar, for about $9: roughly **11 cents per extra good answer**.

**The $25 is a ceiling, not the expected bill.** It assumes every one of the 50 sign-up slots asks 5 questions a week. Answers served from the answer cache (a repeated or reworded question for the same user and data) use no model call at all.

## Prompt caching

### How it works

With prompt caching, Anthropic stores the start of a prompt (the "prefix") for a short time. A later request that begins with exactly the same prefix reads it from the cache instead of processing it again. For Claude Sonnet 5.5:

| | Price per million input tokens | Relative to normal |
|---|---|---|
| Normal input | $2.00 | 1× |
| Writing the prefix to the 5-minute cache | $2.50 | 1.25× |
| Writing the prefix to the 1-hour cache | $4.00 | 2× |
| Reading the prefix from the cache (a "hit") | $0.20 | 0.1× |

The 5-minute cache entry expires 5 minutes after the last request that wrote or read it. Every request that misses pays the higher write price. **Caching saves money only if hits are frequent enough to cover the extra cost of the writes.** With the 5-minute cache, that means at least two requests with the same prefix within 5 minutes of each other.

### What in CreditCoach's prompt could be cached

A typical Sonnet call has about 7,600 input tokens:

| Part | Size | Same for every question? |
|---|---|---|
| System prompt (`system_prompt.md`, 13 KB) and tool definitions | ~4,000 tokens (estimate) | **Yes**: cacheable |
| User profile, memory (which includes today's date), retrieved library passages, prefetched score history and account summary, the question | ~3,600 tokens | **No**: different for every user and question |

Only the fixed half could be cached, about 4,000 tokens per call:
- **Without caching**, that half costs $0.0080 per call.
- **A cache hit** saves $0.0072.
- **A miss on the 5-minute cache** costs an extra $0.0020, for the write.

### Why the 5-minute cache doesn't pay at our traffic

At about 1,000 questions a month, CreditCoach gets about 33 questions a day. Over about 12 active hours, that is roughly one question every 20 minutes.

**If questions arrive at random**, only about **1 in 5** comes within 5 minutes of the one before. The other 4 pay the extra cost of writing the cache:

| | Per question |
|---|---|
| 21% of questions that hit the cache: 0.21 × −$0.0072 | −$0.0015 |
| 79% of questions that miss and write: 0.79 × +$0.0020 | +$0.0016 |
| **Net** | **about $0.0000** |

**So the 5-minute cache saves nothing at this traffic.** The answers that call the model twice (a guardrail rewrite or saving a goal, about 8% of answers) would hit the cache on their second call. That saves about **$0.60 a month**.

The time saved would also be small. Reading a 4,000-token cached prefix saves well under a second, while our answers spend most of their time writing the reply.

The 5-minute cache starts to pay off only at well over 10,000 questions a month, when questions arrive within minutes of each other through most of the day.

### The 1-hour cache: a small saving, with some engineering cost

The 1-hour cache costs twice the normal price to write, but most questions in the active day would come within an hour of the one before:

- Assume about 4 misses a day: the first question of the day, plus a few after long lulls.
- That costs 4 × (+$0.0080) = +$0.032 a day.
- About 29 hits save 29 × $0.0072 = $0.21 a day.

**That is about $5 a month saved at the full sign-up cap, or roughly 20% of the Sonnet bill.** At today's lower real traffic, the saving is smaller.

We still didn't do it now, because:

- **It needs Anthropic-specific code.** CreditCoach calls models through OpenRouter in the OpenAI message format. Caching would need:
  - `cache_control` markers added to the system message's content blocks;
  - the system prompt kept byte-for-byte identical, so that anything that changes per request goes after the marker;
  - a check that OpenRouter passes the 1-hour cache option through.
- **It ties us to a single provider.** `FALLBACK_MODEL` (GPT-4o) and any future model switch would ignore the markers.
- **The answer cache already handles the biggest repeat case.** A repeated or reworded question for the same user and data skips the model call entirely, and so saves the full $0.025 rather than $0.007.
- **The saving is at most about $5 a month** at the cap, and less at today's traffic.

## Decision

- **`CHAT_MODEL=anthropic/claude-sonnet-5.5`.** It is the only model tested that met the 15 s target without losing eval cases.
- **No prompt caching for now.**
- **Revisit both if:**
  - **Repeat eval runs show Terra's 4-case gap is noise.** This was one 50-case run per model, and Task 30 found several cases that flip from run to run on the same model. Two more runs each for Terra and Sonnet would cost about $4 and settle it. If Terra's score matches Sonnet's, switch to Terra and save about $9 a month.
  - **Traffic grows well past the sign-up cap**, or answers arrive within minutes of each other through the day. At that point, add the 1-hour cache on the system prompt.

## Sources

- Eval runs: `docs/evidence/week-4/runs/eval-model-*.json` and the reports linked above.
- Latency and cost per call: Langfuse generations, 2026-10-25 to 2026-11-01. Sonnet 5.5's median call was 7,611 input tokens, 745 output tokens and $0.0229. 102 of 111 answers made a single call.
- Model comparison chart: the "CreditCoach Cost and Speed" dashboard.
- Prompt caching prices and expiry times: Anthropic's prompt-caching documentation for Claude Sonnet 5.5. Cached input is read at 0.1× and written at 1.25× (5 minutes) or 2× (1 hour), and the minimum cacheable prefix is 512 tokens.
