# Why CreditCoach routes between Claude Sonnet 5.5 and DeepSeek V4.1 Flash, and why it doesn't use prompt caching

*2026-11-06 · Decisions: Sonnet 5.5 on 2026-10-31, the router on 2026-11-06 · Code: `creditcoach/agent/router.py`, `creditcoach/config.py` (`CHAT_MODEL`, `FAST_MODEL`, `CREDITCOACH_ROUTER`) · Runner: `scripts/model_benchmark.py` · Dashboard: Dashboard tab → Cost and speed → "Cost against speed and quality"*

## Summary

CreditCoach answers each question with one of two models, chosen before the answer is written:

- **Claude Sonnet 5.5** (`CHAT_MODEL`) answers the questions where a wrong word costs most: anything the input rails flag (a predatory product, an attempt to switch the rules off, a question about how CreditCoach is built), goals and memory, and arithmetic over the user's figures.
- **DeepSeek V4.1 Flash** (`FAST_MODEL`), an open-weight model at high thinking, answers everything else. It is called only through providers that keep no data.

On the same 50-case eval, the router scores the same as Sonnet alone, answers faster, and costs about 40% less on the eval's questions and about 55% less on real traffic:

| | Before: Sonnet 5.5 alone | Now: router | Change |
|---|---|---|---|
| Eval cases passed (3 runs each) | 45, 44, 46 (average 45.0) | 45, 43, 45 (average 44.3) | within Sonnet's own run-to-run spread |
| Median response time | 9.7 s | 8.6 s | −1.1 s |
| 90th percentile | 13.9 s | 12.2 s | −1.7 s |
| Cost per answer, the eval's questions | $0.0255 | $0.0151 | −41% |
| Cost per answer, real traffic (estimate) | $0.0255 | about $0.011 | about −55% |
| Per 1,000 questions, real traffic | about $26 | about $12 | |
| Red team (31 attacks, 5 benign controls) | 31/31 held, 5/5 passed | 31/31 held, 5/5 passed | same |

Guardrail reviews add about $0.0003 to each answer on top of these figures.

The target was **$0.015 per question, without losing response time (about 15 s) or answer quality**. The router meets all three on real traffic. On the eval it sits right at the cost line, because the eval deliberately over-weights the risky and goal questions that go to Sonnet.

How we got here took two rounds of testing: **37 runs of the 50-case eval (1,850 answers), 17 speed screens and 4 red-team runs, across 21 models.** Every run is listed in [All results](#all-results) and on the dashboard.

## The constraint

The brief has two parts:

1. **Response time.** The first persona test showed answers taking about 30 s, one 58 s ([persona-test-fixes.md](persona-test-fixes.md)). The target is about 15 s for 90% of answers.
2. **Quality.** The 50-case eval score may not drop. In round 1 the bar was GPT-5's 43/50 ([eval-effort-low.md](eval-effort-low.md), Task 30); in round 2 it was Sonnet's own same-day score.

Round 2 added a third: **cost of $0.015 per question.** Sonnet alone can't reach it. Its prompt is about 7,600 tokens, and at $2 per million input tokens that alone costs $0.0152, before it writes a word.

## Round 1 (2026-10-27 to 31): Sonnet 5.5 replaces GPT-5

| Model | Eval passed | Median | 90th pct | Cost per answer |
|---|---|---|---|---|
| GPT-5, low thinking (before) | 43/50 | 20.4 s | 30.8 s | $0.0118 |
| GPT-5, minimal thinking | 39/50 | 12.3 s | 18.6 s | $0.0069 |
| **Claude Sonnet 5.5** | **43/50** | **10.4 s** | **14.9 s** | $0.0256 |
| GPT-5.6 Terra | 39/50 | 6.8 s | 10.9 s | $0.0159 |
| Gemini 3.8 Flash | 41/50 | 9.7 s | 17.6 s | $0.0067 |
| Claude Haiku 5.5 | 36/50 | 9.2 s | 12.2 s | $0.0013 |

Sonnet was the only model that matched GPT-5's score and met the time target. It halved the response time at about 2.2× the cost. Why each alternative lost:

- **GPT-5** was the latency bug: 37 of 50 answers took over 15 s. `minimal` thinking was faster but scored 39.
- **GPT-5.6 Terra** was the fastest, but passed 4 fewer cases. It writes short answers (a median of 270 output tokens against Sonnet's 745), and five of its six telling failures were things it left out. One was core: on "How much do I need to pay to get under 30%?" it refused to use the user's data, and the guardrail layer blocked the answer.
- **Gemini 3.8 Flash** scored 41, but 10 of 50 answers took over 15 s, and it once rejected the guardrail rewrite request.
- **Claude Haiku 5.5** was the cheapest, but scored 36.

A speed screen on 8 questions also covered GPT-5.6 Luna (median 9.8 s), which was dropped because Terra was faster. Sonnet held all 31 red-team attacks and passed all 5 controls ([task-21-guardrail-tests.md](../week-3/task-21-guardrail-tests.md)). Full reports: [Sonnet 5.5](eval-model-claude-sonnet-5-5.md), [GPT-5.6 Terra](eval-model-gpt-5-6-terra.md), [Gemini 3.8 Flash](eval-model-gemini-3-8-flash.md), [Haiku 5.5](eval-model-claude-haiku-5-5.md).

## Round 2 (2026-11-05 and 06): open-weight models, then the router

### How the models were tested

Every run used the real pipeline: the guardrail layer on, the answer cache off, memory in a temporary folder, and the same judge (GPT-5 mini). Runs went one at a time, so they didn't compete for the machine and slow each other down. The runner is [scripts/model_benchmark.py](../../../scripts/model_benchmark.py). Two settings mattered for the open-weight models:

- **Thinking.** Most open-weight models think by default, and the pipeline only set thinking for GPT-5. We set it explicitly per run: off, low, medium or high.
- **Where the model runs.** An open-weight model is served by many hosts, and OpenRouter's default routing favours the cheapest. Every open-weight run went only to **zero-data-retention** hosts (`provider: {"zdr": true}`), because in production these models would see real users' credit data. Two models had no such host and were left out for that reason (Qwen3.8 Flash, Qwen3.7 Plus).

The steps were:

1. **Speed screen**: 8 questions per model.
2. **Full eval**: the 50 cases for every model fast and cheap enough, first with thinking low or off, then with thinking on.
3. **Repeats**: of the closest challenger and of Sonnet, because a single 50-case run moves by a few cases. Sonnet itself scored 45, 44 and 46 on the same code.
4. **Red team**: the 31 attacks and 5 controls on the finalists.

Sonnet was re-run as a same-day baseline. It scored 45 on average, not the 43 of round 1, so round 2's bar was higher.

### Speed screen (8 questions each)

| Model | Setting | Median | Slowest | Cost per answer | Carried forward |
|---|---|---|---|---|---|
| Claude Sonnet 5.5 | default | 10.4 s | 20.1 s | $0.0266 | Baseline |
| Qwen3.8 27B | thinking off | 5.0 s | 7.5 s | $0.0024 | Yes |
| DeepSeek V4.1 Flash | thinking off | 4.4 s | 10.6 s | $0.0017 | Yes |
| MiniMax M3 | thinking off | 4.8 s | 6.2 s | $0.0012 | Yes |
| Nemotron 3.5 Super VL | thinking off | 6.0 s | 6.5 s | $0.0011 | Yes |
| Nemotron 3 Ultra 550B | thinking off | 6.8 s | 14.6 s | $0.0049 | Yes |
| Mistral Large 4 | default | 11.2 s | 35.8 s | $0.0064 | No: slowest answer 35.8 s, one answer blocked |
| GLM 5.3 | low thinking | 7.5 s | 29.1 s | $0.0122 | Yes |
| GLM 5.3 Flash | low thinking | 4.8 s | 17.7 s | $0.0010 | Yes |
| MiniMax M3.1 Flash | low thinking | 11.4 s | 15.5 s | $0.0009 | No: slow, one answer blocked |
| GPT-6.1 Terra (closed, for comparison) | thinking off | 4.1 s | 9.9 s | $0.0080 | Yes |

Qwen3.8 2.4T, the largest Qwen, was left out before the screen: at $2/$6 per million tokens it would cost about $0.016 an answer, and it took 14 s on a two-sentence test prompt.

### Full eval: no open-weight model matched Sonnet

| Model | Setting | Runs | Passed (average) | Median | 90th pct | Cost per answer |
|---|---|---|---|---|---|---|
| **Claude Sonnet 5.5** | default | 3 | **45.0** (45, 44, 46) | 9.7 s | 13.9 s | $0.0255 |
| **DeepSeek V4.1 Flash** | high thinking | 4 | **41.8** (44, 45, 38, 40) | 5.1 s | 8.4 s | $0.0013 |
| DeepSeek V4.1 Flash | medium thinking | 1 | 41 | 5.0 s | 7.4 s | $0.0016 |
| Kimi K2.6 | medium thinking | 1 | 41 | 9.4 s | 21.6 s | $0.0083 |
| MiMo V2.6 Pro | medium thinking | 1 | 41 | 17.5 s | 36.0 s | $0.0097 |
| DeepSeek V4.1 Flash 1017 (newer checkpoint) | high thinking | 3 | 39.3 (39, 38, 41) | 6.2 s | 12.1 s | $0.0016 |
| DeepSeek V4.1 Flash | thinking off | 1 | 39 | 5.5 s | 9.5 s | $0.0014 |
| GLM 5.3 Flash | medium thinking | 1 | 39 | 9.5 s | 17.1 s | $0.0011 |
| Gemini 3.8 Flash (closed, re-run) | default | 1 | 39 | 10.1 s | 20.7 s | $0.0079 |
| GLM 5.3 | low thinking | 1 | 38 | 7.2 s | 21.9 s | $0.0091 |
| GLM 5.3 Flash | low thinking | 1 | 37 | 5.3 s | 9.2 s | $0.0011 |
| DeepSeek V4 Pro | medium thinking | 1 | 37 | 12.2 s | 20.5 s | $0.0107 |
| Qwen3.8 27B | medium thinking | 1 | 36 | 5.7 s | 11.1 s | $0.0056 |
| Qwen3.8 27B | thinking off | 1 | 36 | 6.0 s | 11.6 s | $0.0037 |
| MiniMax M3 | thinking off | 1 | 34 | 4.4 s | 6.3 s | $0.0012 |
| Nemotron 3.5 Super VL | thinking off | 1 | 34 | 4.9 s | 6.8 s | $0.0011 |
| Nemotron 3 Ultra 550B | thinking off | 1 | 34 | 6.8 s | 13.0 s | $0.0044 |
| DeepSeek V4 Pro 0813 | medium thinking | 1 | 34 | 9.4 s | 15.1 s | $0.0070 |
| GPT-6.1 Terra (closed) | medium thinking | 1 | 29 | 5.5 s | 8.3 s | $0.0076 |
| GPT-6.1 Terra (closed) | thinking off | 1 | 28 | 4.4 s | 5.9 s | $0.0071 |

What the results showed:

- **Qwen isn't an option.** Qwen3.8 27B scored 36 with thinking off and with it on. It also failed on safety: it didn't clearly refuse the payday loan (#4), and the guardrail layer had to block two or three of its answers per run.
- **Thinking matters more than model size for these models.** DeepSeek V4.1 Flash went from 39 (off) to 41 (medium) to 41.8 on average (high), at almost no extra cost. The larger DeepSeek V4 Pro scored lower and took twice as long.
- **DeepSeek V4.1 Flash on high thinking came closest**, at about 1/20 of Sonnet's cost and half its response time. Across its four runs it scored 3.2 cases below Sonnet on average, and it varied more (38 to 45, against Sonnet's 44 to 46).
- **Turning Sonnet's thinking off isn't possible** through OpenRouter: the request is refused, and that run fell back to GPT-4o on every answer. It is listed but not counted.

### Where DeepSeek V4.1 Flash fell short

Reading its answers, not just the scores:

- **It leaked tool markup once in 200 answers.** On #35 its reply to the user was a tool call written out as text (`<｜DSML｜ invoke name="save_goal">…`), and the goal wasn't saved. That case runs without the goal tool, so it is partly an eval quirk; with the tool offered, it saved the goal in 4 of 4 runs. MiniMax M3 did the same on #3 and #5.
- **One arithmetic slip:** "Net over the two months: −20 points (690 → 650)", where the change is −40 (#7).
- **One untrue claim:** "Your saved goal: …" when nothing was saved (#35, one run in four). That answer still passed the eval. Sonnet said it couldn't save the goal in 3 of 3 runs.
- **Some failures were the checks, not the model.** Three of its four #4 failures were keyword misses: each answer refused the payday loan ("no — I'd steer you firmly away"). Its one red-team miss (GUAR-3) was the same: it refused to give a percentage, and the check fired on it quoting a scammer's "70% chance" as a warning. These checks are left as they are, so the scores here are the strict ones.

Its misses clustered in three kinds of question: risky products, goals and memory, and arithmetic over the user's figures. Those are exactly the questions where Sonnet did well, which is what the router uses.

## The router

### How it routes

[router.py](../../../creditcoach/agent/router.py) picks the model before the agent loop runs, from what the input rails found and the question's wording. It uses patterns only, so it adds no model call and no time.

| Route | Goes to | Matches |
|---|---|---|
| flagged | Sonnet 5.5 | Any input-rail finding: a predatory product (G2), an attempt to switch the rules off or insert personal data (S1–S3), a question about how CreditCoach is built (S5) |
| goal | Sonnet 5.5 | Goals, plans and memory: goal, target, remember, save, plan, focus, guarantee, promise; a timeframe ("in 6 months", "by 2027", "next year"); "will I hit…" |
| multi-step | Sonnet 5.5 | Arithmetic over figures or a named period: "how much", "how long", "what if", "if I pay…", "last two months", a month and year, two 3-digit figures |
| general | DeepSeek V4.1 Flash | Everything else |

Three safeguards come with it:

- **The same model writes any guardrail rewrite** of its own draft.
- **A turn from DeepSeek that is a tool call written as text is asked again of Sonnet** (an `llm.tool_markup` event on the trace), so markup never reaches the user.
- **If DeepSeek fails, the answer falls back to Sonnet**, not GPT-4o. DeepSeek is only ever called through zero-data-retention hosts (`llm.FAST_PROVIDER`).

`CREDITCOACH_ROUTER=off` sends every question to Sonnet again.

### Results

| Run | Passed | Median | 90th pct | Cost per answer | Answers by Sonnet / DeepSeek |
|---|---|---|---|---|---|
| [router-1](eval-router-1.md) | 45/50 | 8.7 s | 12.2 s | $0.0156 | 27 / 23 |
| [router-2](eval-router-2.md) | 43/50 | 8.4 s | 12.0 s | $0.0149 | 27 / 23 |
| [router-3](eval-router-3.md) | 45/50 | 8.4 s | 12.4 s | $0.0148 | 27 / 23 |

- **Quality held.** The router averaged 44.3 against Sonnet's 45.0. The 0.7-case gap is inside Sonnet's own spread (44 to 46), and every router run matched or beat round 1's bar of 43. The cases it failed are mostly the ones Sonnet fails too (#21, #24, #35, #39).
- **DeepSeek's share passed 93% (64 of 69); Sonnet's passed 85% (69 of 81).** Sonnet gets the harder questions.
- **No tool markup** reached the user in 150 answers.
- **Red team:** 31/31 attacks held and 5/5 controls passed ([red-team-router.md](red-team-router.md)). 30 of the 38 prompts went to Sonnet, because the input rails flag most attacks.

### What share goes to Sonnet, and what that costs

Cost depends on how many questions go to Sonnet. Sonnet answers cost about $0.0255; DeepSeek answers about $0.0013. So the share Sonnet gets decides the bill, and **the $0.015 target holds while Sonnet gets up to about 55% of questions.**

| Question set | Share to Sonnet | Estimated cost per answer |
|---|---|---|
| The 50 eval questions | 54% (27 of 50) | $0.015 (measured) |
| The 12 example questions in the app | 42% (5 of 12) | about $0.012 |
| Real questions on the deployed app, 60 days to 2026-11-06 | 41% (15 of 37) | about $0.011 |

The real-traffic share comes from only 37 questions, counted without reading them (the script printed totals only). Each answer's route is now on its trace (`router.model`, `router.reason` on the `creditcoach.answer` span), so the share can be checked once more people use the app.

### The cost, in context

| | Per 1,000 questions | Difference from Sonnet alone |
|---|---|---|
| Claude Sonnet 5.5 alone | about $26 | n/a |
| **Router, real traffic** | **about $12** | about −$14 |
| Router, the eval's mix | about $15 | about −$11 |
| GPT-5 (before round 1) | about $12 | about −$14, but 90th percentile 30.8 s |
| DeepSeek V4.1 Flash alone | about $1.60 | about −$24, but 3 cases lower and less consistent |

At the sign-up cap of about 1,000 questions a month, the router saves about $14 a month against Sonnet alone. Answers served from the answer cache cost nothing on either.

### Risks and what to watch

- **The rules were written after seeing the failures**, and scored on the same 50 questions. They route by kind of question, not by case number, but the real test is live use. Watch the share to Sonnet and the 👍/👎 ratings by route.
- **If the share to Sonnet goes above about 55%**, cost goes over $0.015. The fix is to narrow the goal rule, which is the broadest.
- **DeepSeek's licence (MIT) is from secondary sources.** Check the model card before relying on it beyond hosted use.
- **Hosts change.** The zero-data-retention routing is enforced on every call; if no such host is up, the call fails over to Sonnet.

## Prompt caching

### How it works

With prompt caching, Anthropic stores the start of a prompt (the "prefix") for a short time. A later request that begins with exactly the same prefix reads it from the cache instead of processing it again. For Claude Sonnet 5.5:

| | Price per million input tokens | Relative to normal |
|---|---|---|
| Normal input | $2.00 | 1× |
| Writing the prefix to the 5-minute cache | $2.50 | 1.25× |
| Writing the prefix to the 1-hour cache | $4.00 | 2× |
| Reading the prefix from the cache (a "hit") | $0.20 | 0.1× |

A cache entry expires 5 minutes (or 1 hour) after the last request that wrote or read it. Every request that misses pays the higher write price. **Caching saves money only if hits are frequent enough to cover the extra cost of the writes.**

### What could be cached

A typical Sonnet call has about 7,600 input tokens. About 4,000 of them (the system prompt and tool definitions) are the same for every question; the other 3,600 (profile, memory with today's date, passages, the user's figures, the question) differ every time. Only the fixed part could be cached:

- **Without caching**, it costs $0.0080 per call.
- **A cache hit** saves $0.0072.
- **A miss on the 5-minute cache** costs an extra $0.0020, for the write.

### Why it still doesn't pay

At about 1,000 questions a month, CreditCoach gets about 33 questions a day, roughly one every 20 minutes. With the router, Sonnet gets about 4 in 10 of those, so roughly one every 50 minutes.

- **The 5-minute cache saves nothing:** only about 1 Sonnet question in 10 would arrive within 5 minutes of the one before, and the other 9 pay the write premium.
- **The 1-hour cache** would have saved about $5 a month on Sonnet alone. With the router it is about $1: Sonnet gets about 13 questions a day, so about 9 hits save $0.065 a day, and about 4 misses add $0.032.
- **It would still need Anthropic-specific code:** `cache_control` markers on the system message, a system prompt kept byte-for-byte identical, and a check that OpenRouter passes the 1-hour option through.
- **DeepSeek needs none of this.** Its hosts cache repeated prefixes on their own: most of its input tokens in the benchmark were billed as cached.
- **The answer cache already handles the biggest repeat case:** a repeated or reworded question for the same user and data skips the model call entirely.

## Decision

- **`CREDITCOACH_ROUTER=on`, `CHAT_MODEL=anthropic/claude-sonnet-5.5`, `FAST_MODEL=deepseek/deepseek-v4.1-flash` at `FAST_MODEL_EFFORT=high`.** It meets the time target and the cost target on real traffic, without losing eval cases, and held every red-team attack.
- **No prompt caching.**
- **Revisit if:**
  - **the share of questions going to Sonnet passes about 55%** on real traffic, or the 👍/👎 ratings of DeepSeek's answers fall behind Sonnet's;
  - **an open-weight model matches Sonnet's same-day score over 3 runs.** Then it could answer everything, at a fraction of the cost;
  - **traffic grows well past the sign-up cap.** Then the 1-hour cache on Sonnet's system prompt starts to pay.

## All results

Every 50-case eval run behind this choice, with its report. Each report has every answer and why each case passed or failed; the data is in `runs/eval-<run>.json`. Cost per answer is the answer model only (both models for the router). Round 2's runs record each case's cost with the case. Round 1's come from its traces.

| Run | Date | Model | Setting | Passed | Median | 90th pct | Cost per answer |
|---|---|---|---|---|---|---|---|
| [effort-low](eval-effort-low.md) | 10-27 | GPT-5 | low thinking | 43/50 | 20.4 s | 30.8 s | $0.0118 |
| [effort-minimal](eval-effort-minimal.md) | 10-27 | GPT-5 | minimal thinking | 39/50 | 12.3 s | 18.6 s | $0.0069 |
| [model-claude-sonnet-5-5](eval-model-claude-sonnet-5-5.md) | 10-31 | Claude Sonnet 5.5 | default | 43/50 | 10.4 s | 14.9 s | $0.0256 |
| [model-gpt-5-6-terra](eval-model-gpt-5-6-terra.md) | 10-31 | GPT-5.6 Terra | default | 39/50 | 6.8 s | 10.9 s | $0.0159 |
| [model-gemini-3-8-flash](eval-model-gemini-3-8-flash.md) | 10-31 | Gemini 3.8 Flash | default | 41/50 | 9.7 s | 17.6 s | $0.0067 |
| [model-claude-haiku-5-5](eval-model-claude-haiku-5-5.md) | 10-31 | Claude Haiku 5.5 | default | 36/50 | 9.2 s | 12.2 s | $0.0013 |
| [bench-claude-sonnet-5-5-1](eval-bench-claude-sonnet-5-5-1.md) | 11-05 | Claude Sonnet 5.5 | default | 45/50 | 9.8 s | 13.4 s | $0.0260 |
| [bench-claude-sonnet-5-5-2](eval-bench-claude-sonnet-5-5-2.md) | 11-05 | Claude Sonnet 5.5 | default | 44/50 | 9.5 s | 16.2 s | $0.0258 |
| [bench-claude-sonnet-5-5-3](eval-bench-claude-sonnet-5-5-3.md) | 11-05 | Claude Sonnet 5.5 | default | 46/50 | 9.7 s | 12.0 s | $0.0247 |
| [bench-claude-sonnet-5-5-thinking-off](eval-bench-claude-sonnet-5-5-thinking-off.md) | 11-05 | Claude Sonnet 5.5 | thinking off | not counted: refused, every answer fell back to GPT-4o | 6.2 s | 10.9 s | n/a |
| [bench-deepseek-v4-1-flash-high-1](eval-bench-deepseek-v4-1-flash-high-1.md) | 11-05 | DeepSeek V4.1 Flash | high thinking | 44/50 | 5.3 s | 8.3 s | $0.0016 |
| [bench-deepseek-v4-1-flash-high-2](eval-bench-deepseek-v4-1-flash-high-2.md) | 11-05 | DeepSeek V4.1 Flash | high thinking | 45/50 | 5.0 s | 8.9 s | $0.0013 |
| [bench-deepseek-v4-1-flash-high-3](eval-bench-deepseek-v4-1-flash-high-3.md) | 11-05 | DeepSeek V4.1 Flash | high thinking | 38/50 | 5.2 s | 8.5 s | $0.0011 |
| [bench-deepseek-v4-1-flash-high-4](eval-bench-deepseek-v4-1-flash-high-4.md) | 11-05 | DeepSeek V4.1 Flash | high thinking | 40/50 | 4.9 s | 7.0 s | $0.0011 |
| [bench-deepseek-v4-1-flash-medium](eval-bench-deepseek-v4-1-flash-medium.md) | 11-05 | DeepSeek V4.1 Flash | medium thinking | 41/50 | 5.0 s | 7.4 s | $0.0016 |
| [bench-deepseek-v4-1-flash-off](eval-bench-deepseek-v4-1-flash-off.md) | 11-05 | DeepSeek V4.1 Flash | thinking off | 39/50 | 5.5 s | 9.5 s | $0.0014 |
| [bench-deepseek-v4-1-flash-1017-high-1](eval-bench-deepseek-v4-1-flash-1017-high-1.md) | 11-05 | DeepSeek V4.1 Flash 1017 | high thinking | 39/50 | 6.9 s | 12.5 s | $0.0019 |
| [bench-deepseek-v4-1-flash-1017-high-2](eval-bench-deepseek-v4-1-flash-1017-high-2.md) | 11-05 | DeepSeek V4.1 Flash 1017 | high thinking | 38/50 | 6.0 s | 13.3 s | $0.0015 |
| [bench-deepseek-v4-1-flash-1017-high-3](eval-bench-deepseek-v4-1-flash-1017-high-3.md) | 11-05 | DeepSeek V4.1 Flash 1017 | high thinking | 41/50 | 6.2 s | 8.5 s | $0.0013 |
| [bench-deepseek-v4-pro-medium](eval-bench-deepseek-v4-pro-medium.md) | 11-05 | DeepSeek V4 Pro | medium thinking | 37/50 | 12.2 s | 20.5 s | $0.0107 |
| [bench-deepseek-v4-pro-0813-medium](eval-bench-deepseek-v4-pro-0813-medium.md) | 11-05 | DeepSeek V4 Pro 0813 | medium thinking | 34/50 | 9.4 s | 15.1 s | $0.0070 |
| [bench-qwen3-8-27b-off](eval-bench-qwen3-8-27b-off.md) | 11-05 | Qwen3.8 27B | thinking off | 36/50 | 6.0 s | 11.6 s | $0.0037 |
| [bench-qwen3-8-27b-medium](eval-bench-qwen3-8-27b-medium.md) | 11-05 | Qwen3.8 27B | medium thinking | 36/50 | 5.7 s | 11.1 s | $0.0056 |
| [bench-kimi-k2-6-medium](eval-bench-kimi-k2-6-medium.md) | 11-05 | Kimi K2.6 | medium thinking | 41/50 | 9.4 s | 21.6 s | $0.0083 |
| [bench-mimo-v2-6-pro-medium](eval-bench-mimo-v2-6-pro-medium.md) | 11-05 | MiMo V2.6 Pro | medium thinking | 41/50 | 17.5 s | 36.0 s | $0.0097 |
| [bench-glm-5-3-low](eval-bench-glm-5-3-low.md) | 11-05 | GLM 5.3 | low thinking | 38/50 | 7.2 s | 21.9 s | $0.0091 |
| [bench-glm-5-3-flash-low](eval-bench-glm-5-3-flash-low.md) | 11-05 | GLM 5.3 Flash | low thinking | 37/50 | 5.3 s | 9.2 s | $0.0011 |
| [bench-glm-5-3-flash-medium](eval-bench-glm-5-3-flash-medium.md) | 11-05 | GLM 5.3 Flash | medium thinking | 39/50 | 9.5 s | 17.1 s | $0.0011 |
| [bench-minimax-m3-off](eval-bench-minimax-m3-off.md) | 11-05 | MiniMax M3 | thinking off | 34/50 | 4.4 s | 6.3 s | $0.0012 |
| [bench-nemotron-3-5-super-off](eval-bench-nemotron-3-5-super-off.md) | 11-05 | Nemotron 3.5 Super VL | thinking off | 34/50 | 4.9 s | 6.8 s | $0.0011 |
| [bench-nemotron-3-ultra-off](eval-bench-nemotron-3-ultra-off.md) | 11-05 | Nemotron 3 Ultra 550B | thinking off | 34/50 | 6.8 s | 13.0 s | $0.0044 |
| [bench-gemini-3-8-flash](eval-bench-gemini-3-8-flash.md) | 11-05 | Gemini 3.8 Flash | default | 39/50 | 10.1 s | 20.7 s | $0.0079 |
| [bench-gpt-6-1-terra-off](eval-bench-gpt-6-1-terra-off.md) | 11-05 | GPT-6.1 Terra | thinking off | 28/50 | 4.4 s | 5.9 s | $0.0071 |
| [bench-gpt-6-1-terra-medium](eval-bench-gpt-6-1-terra-medium.md) | 11-05 | GPT-6.1 Terra | medium thinking | 29/50 | 5.5 s | 8.3 s | $0.0076 |
| [router-1](eval-router-1.md) | 11-06 | Router | routed | 45/50 | 8.7 s | 12.2 s | $0.0156 |
| [router-2](eval-router-2.md) | 11-06 | Router | routed | 43/50 | 8.4 s | 12.0 s | $0.0149 |
| [router-3](eval-router-3.md) | 11-06 | Router | routed | 45/50 | 8.4 s | 12.4 s | $0.0148 |

Red-team runs (31 attacks, 5 benign controls each):

| Date | Model | Attacks held | Controls passed | Transcripts |
|---|---|---|---|---|
| 10-31 | Claude Sonnet 5.5 | 31/31 | 5/5 | [task-21-red-team.md](../week-3/task-21-red-team.md) |
| 11-05 | Claude Sonnet 5.5 | 31/31 | 5/5 | [red-team-claude-sonnet-5-5.md](red-team-claude-sonnet-5-5.md) |
| 11-05 | DeepSeek V4.1 Flash, high thinking | 30/31 (the miss is a check firing on a refusal, see above) | 5/5 | [red-team-deepseek-v4-1-flash-high.md](red-team-deepseek-v4-1-flash-high.md) |
| 11-06 | Router | 31/31 | 5/5 | [red-team-router.md](red-team-router.md) |

The speed screens are in [runs/model-benchmark-speed-screen.json](runs/model-benchmark-speed-screen.json). Round 2 cost about $16 of OpenRouter credit, judges included: $12.71 on 2026-11-05 and $3.24 on 2026-11-06.

## Sources

- Eval runs: `docs/evidence/week-4/runs/eval-*.json` and the reports linked above. Red-team runs: `runs/red-team-*.json`.
- The dashboard's table and every-run list: [model_comparison.json](../../../creditcoach/evals/model_comparison.json), built from the runs by [scripts/model_comparison.py](../../../scripts/model_comparison.py).
- Round 1 latency and cost per call: Langfuse generations, 2026-10-25 to 2026-11-01. Sonnet 5.5's median call was 7,611 input tokens, 745 output tokens and $0.0229.
- Model prices, hosts and zero-data-retention routes: OpenRouter's model and endpoint listings, 2026-11-05.
- Prompt caching prices and expiry times: Anthropic's prompt-caching documentation for Claude Sonnet 5.5. Cached input is read at 0.1× and written at 1.25× (5 minutes) or 2× (1 hour); the minimum cacheable prefix is 512 tokens.
