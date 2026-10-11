# Task 22 Evidence: Cache Miss, Then Hit

*2026-10-10 · Code: `creditcoach/cache/`, `creditcoach/rag/retrieve.py`, `creditcoach/agent/mcp_host.py`, `creditcoach/agent/pipeline.py` · Design: [docs/caching.md](../../caching.md) · Tests: `tests/test_cache.py` · Script: `uv run python scripts/task22_cache_log.py`*

**Definition of Done:** repeated identical queries hit the cache instead of re-querying.

**Result: ✅ PASS**

Cache store: **Redis 8.10.2 (localhost:6379/0)**. It was emptied before the run (4 keys removed). Every answer is live, from `openai/gpt-5` over MCP, through `pipeline.answer(..., use_cache=True)` as the chat UI calls it.

| # | Step | User | Question | Answer cache | Embedding | Retrieval | Tool lookups | GPT-5 called | Time | As expected |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | A question, first time | USR-001 | Why did my credit score drop 20 points this month? | **miss** | 1 miss, 1 store, 1 hit | 1 miss, 1 store | 2 miss, 2 store | yes | 10.99 s | ✅ |
| 2 | The same question again | USR-001 | Why did my credit score drop 20 points this month? | **hit** (exact) | 1 hit | not used | 2 hit | **no** | 0.01 s | ✅ |
| 3 | The question reworded | USR-001 | My credit score dropped 20 points this month. Why? | **hit** (same words) | 1 miss, 1 store | not used | 2 hit | **no** | 0.03 s | ✅ |
| 4 | A look-alike question | USR-001 | Why did my credit score drop 20 points last month? | **miss** | 1 miss, 1 store, 1 hit | 1 miss, 1 store | 2 hit | yes | 7.17 s | ✅ |
| 5 | A different question, same user | USR-001 | What's my current credit utilization ratio? | **miss** | 1 miss, 1 store, 1 hit | 1 miss, 1 store | 2 hit | yes | 5.55 s | ✅ |
| 6 | The first question, another user | USR-003 | Why did my credit score drop 20 points this month? | **miss** | 1 hit | 1 hit | 2 miss, 2 store | yes | 8.06 s | ✅ |

Read the table as: question 1 misses every layer and stores what it computed. Question 2, the same question, hits the embedding cache and then the answer cache, so nothing is retrieved, no MCP server starts and GPT-5 is not called. Question 3 is a rewording and hits too. Question 4 looks almost the same to the embedding model but asks about another month, so it is answered afresh. Question 5 is new, but the user's score history and account summary come from the cache. Question 6 shows that another user shares nothing.

## Cache log, question by question

Each line is one entry from the `creditcoach.cache` logger, in order.

### 1. A question, first time

Asked as USR-001: *"Why did my credit score drop 20 points this month?"*

```json
{"layer": "embedding", "result": "miss", "key": "cc:1:embedding:3809dca51a1d91744a51836fc5215adc", "ms": 0.32}
{"layer": "embedding", "result": "store", "key": "cc:1:embedding:3809dca51a1d91744a51836fc5215adc", "ttl": 604800}
{"layer": "answer", "result": "miss", "key": "cc:1:answer:USR-001:index", "user_id": "USR-001", "reason": "nothing stored for this user"}
{"layer": "retrieval", "result": "miss", "key": "cc:1:retrieval:a613cf76d6e134751239ecb411cf30a5", "ms": 0.07}
{"layer": "embedding", "result": "hit", "key": "cc:1:embedding:3809dca51a1d91744a51836fc5215adc", "ms": 0.16}
{"layer": "retrieval", "result": "store", "key": "cc:1:retrieval:a613cf76d6e134751239ecb411cf30a5", "ttl": 86400}
{"layer": "tool", "result": "miss", "key": "cc:1:tool:USR-001:483528f5dc895a67af53f15076bf1f96", "ms": 0.4, "tool": "get_score_history", "user_id": "USR-001"}
{"layer": "tool", "result": "store", "key": "cc:1:tool:USR-001:483528f5dc895a67af53f15076bf1f96", "ttl": 300, "tool": "get_score_history", "user_id": "USR-001"}
{"layer": "tool", "result": "miss", "key": "cc:1:tool:USR-001:4ce1b2c633d2252b900d84f89b932085", "ms": 0.15, "tool": "get_account_summary", "user_id": "USR-001"}
{"layer": "tool", "result": "store", "key": "cc:1:tool:USR-001:4ce1b2c633d2252b900d84f89b932085", "ttl": 300, "tool": "get_account_summary", "user_id": "USR-001"}
{"layer": "answer", "result": "store", "key": "cc:1:answer:USR-001:88c4788482174a1b", "user_id": "USR-001", "ttl": 3600, "stored": 1}
```

Answer shown to the user:

> Short answer: Your score fell 20 points this month mainly because of two things together: a new hard inquiry (you applied for credit) plus a jump in your card utilization (the share of your limits being used).
>
> What changed this month
> - Latest score: 650 (2026-09), down 20 points.
> - Factor noted: “Hard inquiry + utilization spike.”
> - Your card usage now: ₹74,750 total on ₹2,00,000 limits = 37.4% overall.
>   - One card is very high: ₹59,000 on a ₹75,000 limit = 78.7%.
>
> Why this hurts your score
> - A hard inquiry typically costs about 2–10 points and fades over ~12 months [1].
> - Utilization above ~30% on a card or overall commonly causes short-term drops (often 10–40 points) [3]. The effect usually eases after the lower balance is reported next cycle.
>
> Quick fixes to focus on
> 1) Pay down the high card first: Bring the ₹75,000-limit card below 30% (≤₹22,500). Even getting overall usage under 30% (≤₹60,000 total) would help—today you’re at ₹74,750, so a paydown of at least ₹14,750 gets you under that mark. Lower (10–20%) is even better.
> 2) Time your payments: Pay before the statement date so a lower balance is what gets reported [3].
> 3) Pause new applications: Let the inquiry age; avoid further credit applications for now [1].
>
> If anything here doesn’t look familiar (for example, the inquiry), check your credit report and dispute errors for free [2].

### 2. The same question again

Asked as USR-001: *"Why did my credit score drop 20 points this month?"*

```json
{"layer": "embedding", "result": "hit", "key": "cc:1:embedding:3809dca51a1d91744a51836fc5215adc", "ms": 0.24}
{"layer": "tool", "result": "hit", "key": "cc:1:tool:USR-001:483528f5dc895a67af53f15076bf1f96", "ms": 0.12, "tool": "get_score_history", "user_id": "USR-001"}
{"layer": "tool", "result": "hit", "key": "cc:1:tool:USR-001:4ce1b2c633d2252b900d84f89b932085", "ms": 0.14, "tool": "get_account_summary", "user_id": "USR-001"}
{"layer": "answer", "result": "hit", "key": "cc:1:answer:USR-001:88c4788482174a1b", "user_id": "USR-001", "how": "exact", "similarity": 1.0, "matched_question": "Why did my credit score drop 20 points this month?", "age_seconds": 0, "saved_seconds": 10.9}
```

Served the answer stored for *"Why did my credit score drop 20 points this month?"* (exact, similarity 1.0, stored 0 s earlier), after checking the user's figures are unchanged. The original took 10.9 s.

Answer shown to the user (identical to the first):

> Short answer: Your score fell 20 points this month mainly because of two things together: a new hard inquiry (you applied for credit) plus a jump in your card utilization (the share of your limits being used).
>
> What changed this month
> - Latest score: 650 (2026-09), down 20 points.
> - Factor noted: “Hard inquiry + utilization spike.”
> - Your card usage now: ₹74,750 total on ₹2,00,000 limits = 37.4% overall.
>   - One card is very high: ₹59,000 on a ₹75,000 limit = 78.7%.
>
> Why this hurts your score
> - A hard inquiry typically costs about 2–10 points and fades over ~12 months [1].
> - Utilization above ~30% on a card or overall commonly causes short-term drops (often 10–40 points) [3]. The effect usually eases after the lower balance is reported next cycle.
>
> Quick fixes to focus on
> 1) Pay down the high card first: Bring the ₹75,000-limit card below 30% (≤₹22,500). Even getting overall usage under 30% (≤₹60,000 total) would help—today you’re at ₹74,750, so a paydown of at least ₹14,750 gets you under that mark. Lower (10–20%) is even better.
> 2) Time your payments: Pay before the statement date so a lower balance is what gets reported [3].
> 3) Pause new applications: Let the inquiry age; avoid further credit applications for now [1].
>
> If anything here doesn’t look familiar (for example, the inquiry), check your credit report and dispute errors for free [2].

### 3. The question reworded

Asked as USR-001: *"My credit score dropped 20 points this month. Why?"*

```json
{"layer": "embedding", "result": "miss", "key": "cc:1:embedding:67b97a7e6d9d74760ab90cceb4cdd2dc", "ms": 0.15}
{"layer": "embedding", "result": "store", "key": "cc:1:embedding:67b97a7e6d9d74760ab90cceb4cdd2dc", "ttl": 604800}
{"layer": "tool", "result": "hit", "key": "cc:1:tool:USR-001:483528f5dc895a67af53f15076bf1f96", "ms": 0.09, "tool": "get_score_history", "user_id": "USR-001"}
{"layer": "tool", "result": "hit", "key": "cc:1:tool:USR-001:4ce1b2c633d2252b900d84f89b932085", "ms": 0.07, "tool": "get_account_summary", "user_id": "USR-001"}
{"layer": "answer", "result": "hit", "key": "cc:1:answer:USR-001:88c4788482174a1b", "user_id": "USR-001", "how": "same words", "similarity": 0.985, "matched_question": "Why did my credit score drop 20 points this month?", "age_seconds": 0, "saved_seconds": 10.9}
```

Served the answer stored for *"Why did my credit score drop 20 points this month?"* (same words, similarity 0.985, stored 0 s earlier), after checking the user's figures are unchanged. The original took 10.9 s.

### 4. A look-alike question

Asked as USR-001: *"Why did my credit score drop 20 points last month?"*

```json
{"layer": "embedding", "result": "miss", "key": "cc:1:embedding:69c3ecfcf1062daaf2485b6d84829034", "ms": 0.13}
{"layer": "embedding", "result": "store", "key": "cc:1:embedding:69c3ecfcf1062daaf2485b6d84829034", "ttl": 604800}
{"layer": "answer", "result": "miss", "key": "cc:1:answer:USR-001:index", "user_id": "USR-001", "reason": "time words differ from the closest stored question (0.996 similar)"}
{"layer": "retrieval", "result": "miss", "key": "cc:1:retrieval:d7b21b792724fbeda97254c5f4da3767", "ms": 0.09}
{"layer": "embedding", "result": "hit", "key": "cc:1:embedding:69c3ecfcf1062daaf2485b6d84829034", "ms": 0.15}
{"layer": "retrieval", "result": "store", "key": "cc:1:retrieval:d7b21b792724fbeda97254c5f4da3767", "ttl": 86400}
{"layer": "tool", "result": "hit", "key": "cc:1:tool:USR-001:483528f5dc895a67af53f15076bf1f96", "ms": 0.4, "tool": "get_score_history", "user_id": "USR-001"}
{"layer": "tool", "result": "hit", "key": "cc:1:tool:USR-001:4ce1b2c633d2252b900d84f89b932085", "ms": 0.13, "tool": "get_account_summary", "user_id": "USR-001"}
{"layer": "answer", "result": "store", "key": "cc:1:answer:USR-001:5c028f0abc4e4a39", "user_id": "USR-001", "ttl": 3600, "stored": 2}
```

Not served from the cache: time words differ from the closest stored question (0.996 similar). A stored answer about this month would have been wrong for last month.

### 5. A different question, same user

Asked as USR-001: *"What's my current credit utilization ratio?"*

```json
{"layer": "embedding", "result": "miss", "key": "cc:1:embedding:9abafdc026b2c2dc8d5fa1d2a978af49", "ms": 0.21}
{"layer": "embedding", "result": "store", "key": "cc:1:embedding:9abafdc026b2c2dc8d5fa1d2a978af49", "ttl": 604800}
{"layer": "answer", "result": "miss", "key": "cc:1:answer:USR-001:index", "user_id": "USR-001", "reason": "closest stored question is 0.433 similar, below 0.9"}
{"layer": "retrieval", "result": "miss", "key": "cc:1:retrieval:c454e33c6a2b04ee98af1a7c40da1a8d", "ms": 0.08}
{"layer": "embedding", "result": "hit", "key": "cc:1:embedding:9abafdc026b2c2dc8d5fa1d2a978af49", "ms": 0.24}
{"layer": "retrieval", "result": "store", "key": "cc:1:retrieval:c454e33c6a2b04ee98af1a7c40da1a8d", "ttl": 86400}
{"layer": "tool", "result": "hit", "key": "cc:1:tool:USR-001:483528f5dc895a67af53f15076bf1f96", "ms": 0.37, "tool": "get_score_history", "user_id": "USR-001"}
{"layer": "tool", "result": "hit", "key": "cc:1:tool:USR-001:4ce1b2c633d2252b900d84f89b932085", "ms": 0.16, "tool": "get_account_summary", "user_id": "USR-001"}
{"layer": "answer", "result": "store", "key": "cc:1:answer:USR-001:0a177cf973054e2a", "user_id": "USR-001", "ttl": 3600, "stored": 3}
```

### 6. The first question, another user

Asked as USR-003: *"Why did my credit score drop 20 points this month?"*

```json
{"layer": "embedding", "result": "hit", "key": "cc:1:embedding:3809dca51a1d91744a51836fc5215adc", "ms": 0.19}
{"layer": "answer", "result": "miss", "key": "cc:1:answer:USR-003:index", "user_id": "USR-003", "reason": "nothing stored for this user"}
{"layer": "retrieval", "result": "hit", "key": "cc:1:retrieval:a613cf76d6e134751239ecb411cf30a5", "ms": 0.12}
{"layer": "tool", "result": "miss", "key": "cc:1:tool:USR-003:483528f5dc895a67af53f15076bf1f96", "ms": 0.29, "tool": "get_score_history", "user_id": "USR-003"}
{"layer": "tool", "result": "store", "key": "cc:1:tool:USR-003:483528f5dc895a67af53f15076bf1f96", "ttl": 300, "tool": "get_score_history", "user_id": "USR-003"}
{"layer": "tool", "result": "miss", "key": "cc:1:tool:USR-003:4ce1b2c633d2252b900d84f89b932085", "ms": 0.26, "tool": "get_account_summary", "user_id": "USR-003"}
{"layer": "tool", "result": "store", "key": "cc:1:tool:USR-003:4ce1b2c633d2252b900d84f89b932085", "ttl": 300, "tool": "get_account_summary", "user_id": "USR-003"}
{"layer": "answer", "result": "store", "key": "cc:1:answer:USR-003:9490d724b3a245a3", "user_id": "USR-003", "ttl": 3600, "stored": 1}
```

## Counters and what is stored afterwards

| Layer | Hits | Misses | Stores | Hit rate | Keys now | Time to live |
|---|---|---|---|---|---|---|
| embedding | 5 | 4 | 4 | 0.556 | 4 | 604,800 s |
| answer | 2 | 4 | 4 | 0.333 | 6 | 3,600 s |
| retrieval | 1 | 3 | 3 | 0.25 | 3 | 86,400 s |
| tool | 8 | 4 | 4 | 0.667 | 4 | 300 s |

Hit rates over six scripted questions only show that the counters work. Task 23 measures the hit rate and the latency improvement properly.

