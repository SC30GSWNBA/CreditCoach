# Task 23 Evidence: Cache Hit Rate and Latency

*2026-10-10 · Code: `creditcoach/cache/` · Design: [docs/caching.md](../../caching.md) · Script: `uv run python scripts/task23_cache_latency.py` · Data: [task-23-cache-latency.json](runs/task-23-cache-latency.json)*

**Definition of Done:** latency compared for cached vs. uncached calls with documented improvement.

**Result: ✅ PASS**

| | Uncached (first time) | Cached (repeated) | Improvement |
|---|---|---|---|
| **Answer latency, median** | **11.05 s** | **0.009 s** | **1,228× faster** (11.0 s saved) |
| Answer latency, range | 5.55 to 22.23 s | 0.007 to 0.015 s | |
| GPT-5 calls per answer | 1.1 | 0 | |
| Model cost per answer, mean | $0.0122 | $0 | 100% |
| Tokens per answer, mean (in / out) | 5,877 / 1,058 | 0 / 0 | |

Measured live on 2026-10-10 19:40 with `openai/gpt-5` (reasoning effort `low`) over MCP, the guardrail layer on, and the cache in **Redis 8.10.2 (localhost:6379/0)**, emptied first. Requests ran one at a time through `pipeline.answer(..., use_cache=True)`, as the chat UI calls it. Costs are what OpenRouter reported for each call, in US dollars, and include the guardrail layer's wording review.

## 1. Hit rate on the workload

35 requests in four passes. The hit rate depends entirely on how often users repeat themselves, so these figures describe this workload, not real traffic.

| Pass | Requests | Answer-cache hits | Hit rate | Median time | Model cost |
|---|---|---|---|---|---|
| 1. First time (cache empty) | 10 | 0 | 0% | 11.05 s | $0.1223 |
| 2. Repeated word for word | 10 | 10 | 100% | 0.01 s | $0.0000 |
| 3. Reworded, same meaning | 10 | 10 | 100% | 1.31 s | $0.0006 |
| 4. Look-alike, different meaning | 5 | 0 (a hit would be a wrong answer) | 0% | 11.62 s | $0.0610 |
| **All four passes** | **35** | **20** | **57%** | | **$0.1840** |
| After the first pass (2 to 4) | 25 | 20 | 80% | | |

- **Wrong hits: 0.** None of the 5 look-alike questions was served from the cache.
- **Repeats: 10 of 10 hit**, each with the answer identical to the first.
- **Rewordings: 10 of 10 hit.** 2 by same words (median 0.04 s); 8 by model-confirmed (median 1.38 s). A rewording that isn't recognised is answered afresh: slower, never wrong.
- **Without the cache**, 35 requests at the first-pass averages would have taken about 6.8 minutes of waiting and $0.43. With it they took 3.0 minutes and $0.18: **55% less time and 57% less cost** on this workload.

Hits and misses per layer over the whole workload, from the cache's own counters:

| Layer | Hits | Misses | Hit rate | Stores |
|---|---|---|---|---|
| embedding | 28 | 25 | 53% | 25 |
| retrieval | 0 | 18 | 0% | 18 |
| tool | 62 | 8 | 89% | 8 |
| answer | 20 | 15 | 57% | 15 |

The tool layer keeps a result for 5 minutes, so some of its misses are lookups that had expired by the time a later pass reached that user, not new work.

## 2. Latency, request by request

| Query | User | Pass 1: first time | Pass 2: repeated | Faster | Pass 3: reworded | How the rewording matched |
|---|---|---|---|---|---|---|
| #1 Why did my credit score drop 20 points this month? | USR-001 | 11.48 s | 0.015 s (hit) | 766× | 0.03 s (hit) | same words (0.985) |
| #2 What's my current credit utilization ratio? | USR-001 | 5.55 s | 0.013 s (hit) | 427× | 1.53 s (hit) | model-confirmed (0.976) |
| #3 I want to buy a car in 12 months — what should I focus on? | USR-001 | 14.39 s | 0.011 s (hit) | 1,308× | 1.40 s (hit) | model-confirmed (0.979) |
| #4 Should I take out this payday loan to pay off my credit card? | USR-001 | 10.62 s | 0.009 s (hit) | 1,180× | 1.27 s (hit) | model-confirmed (0.962) |
| #6 Can you guarantee my score will hit 720 if I do what you said? | USR-001 | 22.23 s | 0.009 s (hit) | 2,470× | 1.16 s (hit) | model-confirmed (0.935) |
| #9 Why did my score dip the last two months? I've always paid on time. | USR-003 | 7.88 s | 0.009 s (hit) | 875× | 1.12 s (hit) | model-confirmed (0.954) |
| #29 Can I take another instant loan app loan to pay this month's card bill? | USR-012 | 9.64 s | 0.008 s (hit) | 1,204× | 1.55 s (hit) | model-confirmed (0.964) |
| #31 What is a payday loan and how does it work? | USR-001 | 11.65 s | 0.008 s (hit) | 1,457× | 1.36 s (hit) | model-confirmed (0.968) |
| #33 Is a balance transfer a good idea for my 79% card? | USR-001 | 9.65 s | 0.008 s (hit) | 1,206× | 0.05 s (hit) | same words (0.991) |
| #42 When exactly will my score be back to 811? | USR-009 | 12.93 s | 0.007 s (hit) | 1,847× | 1.44 s (hit) | model-confirmed (0.988) |

Rewordings asked in pass 3:

- #1: *"My credit score dropped 20 points this month. Why?"*
- #2: *"What is my credit utilization ratio right now?"*
- #3: *"I'd like to buy a car in 12 months. What should I focus on?"*
- #4: *"Should I take a payday loan to pay off my credit card?"*
- #6: *"Can you guarantee that my score will reach 720 if I follow your advice?"*
- #9: *"Why has my score dipped over the last two months? I have always paid on time."*
- #29: *"Is it OK to take another instant loan app loan to pay this month's card bill?"*
- #31: *"How does a payday loan work?"*
- #33: *"Would a balance transfer be a good idea for my 79% card?"*
- #42: *"When exactly is my score going to be back at 811?"*

Look-alike questions (pass 4), all answered afresh:

| Base query | Look-alike question | Result | Why it wasn't matched | Time |
|---|---|---|---|---|
| #1 | Why did my credit score drop 20 points last month? | miss | time words differ from the closest stored question (0.996 similar) | 11.62 s |
| #2 | What should my credit utilization ratio be? | miss | closest stored question (0.924 similar) was not confirmed as the same | 7.96 s |
| #3 | I want to buy a car in 6 months — what should I focus on? | miss | numbers differ from the closest stored question (0.915 similar) | 13.44 s |
| #6 | Can you guarantee my score will hit 750 if I do what you said? | miss | closest stored question is 0.785 similar, below 0.9 | 7.94 s |
| #33 | Is a balance transfer a good idea for my 19% card? | miss | closest stored question is 0.862 similar, below 0.9 | 13.00 s |

A model-confirmed hit includes one `openai/gpt-5-mini` call to check the two questions ask the same thing: median 1.38 s and $0.00008 a hit, against 11.1 s and $0.0122 for a fresh answer.

1 first-pass answer(s) were rewritten by the guardrail layer (#6), which is why they took longest.

## 3. Each layer on its own

The work a layer replaces, against reading the cached value, 30 repetitions each (10 for the MCP round trip), no model call.

| Layer | What is measured | Uncached, median | Cached, median | Faster | Saved per use |
|---|---|---|---|---|---|
| embedding | Embedding one question with the local model | 4.73 ms | 0.25 ms | 18.8× | 4.5 ms |
| retrieval | Vector search and reranking for one question | 20.51 ms | 0.15 ms | 137.5× | 20.4 ms |
| tool | Starting the MCP server, which reads the dataset from Neon, and fetching score history and account summary | 1823.05 ms | 0.29 ms | 6252.7× | 1822.8 ms |
| answer | A whole answer (from §2) | 11,051 ms | 9.0 ms | 1,228× | 11,042 ms |

The answer layer saves 11 seconds, because the model is almost all of an answer's time. Of the other three, only the tool layer is noticeable: with the dataset in Neon, fetching a user's figures over MCP takes 1.8 s, and an answer-cache hit needs those figures to check the stored answer is still right. Reading them from the cache is why a hit takes milliseconds. The retrieval layer shows 0 hits in §1 because it is only reached when the answer cache misses, and in this workload every miss was a question not asked before.

## 4. What these numbers do and don't show

- **The speed-up is real and repeatable**: every word-for-word repeat hit, and a hit never called GPT-5.
- **The hit rate is the workload's.** Two thirds of these requests were deliberate repeats or rewordings. Real users repeat far less, so the saving in production would be smaller. The demo's repeated factor-lookup question is the case this is built for.
- **Evaluation runs are not cached** (docs/caching.md §3), so this does not yet reduce what an eval run costs.
- **One machine, one run, one request at a time.** Uncached times vary with the model provider (5.5 to 22.2 s here). Cached times depend on a local Redis; a remote one would add its network round trips.
- **Sample sizes are small**: 10 questions per pass, so medians and ranges are given, not percentiles.

