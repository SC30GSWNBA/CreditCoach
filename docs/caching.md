# CreditCoach: Caching

*Week 3 · Task #22 · Last updated: 2026-10-10 · Status: Draft for team review · Code: `creditcoach/cache/`*

An answer takes about 11 seconds and one GPT-5 call. Almost all of that is the model. This document defines what CreditCoach caches so repeated work isn't done twice, and the rules that keep a cached answer from being a wrong answer. Task #23 measures the hit rate and the latency improvement, and since Task #25 the chat UI shows a cache badge above each answer ([screenshots](evidence/week-3/task-25-badges.md)).

## 1. What is cached

Four layers. The first three are exact-match caches of deterministic work. The fourth is the semantic cache.

| Layer | What is stored | Key | Kept for | Saves |
|---|---|---|---|---|
| **Embedding** | A question's embedding vector (384 numbers) | Embedding model + question text | 7 days | About 5 ms |
| **Retrieval** | The passages retrieved for a question | Corpus fingerprint + both local models + question + retrieval options | 24 hours | About 20 ms (search and rerank) |
| **Tool** | A successful `get_score_history` or `get_account_summary` result | **User** + tool + arguments + data backend | 5 minutes | About 1.8 s when the dataset is in Neon (0.4 s from files): the MCP server start and its read of the dataset |
| **Answer** | A finished, guardrail-checked answer with its passages and sources | **User** + question (exact or same meaning, §3) | 1 hour | About 11 s and one GPT-5 call |

The times are measured on this machine in Task 23 ([task-23-cache-latency.md](evidence/week-3/task-23-cache-latency.md)). They show where caching matters: the answer layer is the one a user sees. The other three make a cache hit possible (the answer lookup needs the embedding and the user's live figures) and keep a miss from repeating small work.

Tasks.md asks for "RAG embeddings and frequent score-factor lookups". The embedding and retrieval layers are the first. The tool layer is the second: the score history with its factor for each month, and the account summary, which nearly every question needs. The answer layer is the implementation plan's semantic cache: the same user asking the same question again is served from the cache instead of the model.

## 2. Where it is stored and how it is read

- **Redis**, when `REDIS_URL` is set (`redis://localhost:6379/0` for a local install: `brew install redis && brew services start redis`). Redis keeps the cache across app restarts and shares it between processes.
- **The app's own memory**, when `REDIS_URL` isn't set, so a fresh clone runs with no Redis. It is lost on restart and capped at 5,000 entries, least recently used first.
- Every value is JSON under a key of the form `cc:<schema>:<layer>:[<user>:]<digest>`. Per-user layers have the user ID in the key, so one user's entries can be listed or cleared (`cache.clear("answer", "USR-001")`) and can never be read under another user's key. Raising `SCHEMA` in the code abandons everything cached by older code.
- Every read and write goes through `cache.get` and `cache.put`, which log one JSON line on the `creditcoach.cache` logger, count hits, misses and stores per layer (`cache.stats()`), and attach the turn's lookups to the answer (`Answer.cache`).
- **The cache can never break an answer.** A Redis error is logged and treated as a miss, and Redis is then left alone for 30 seconds so a dead server costs one short timeout, not one per lookup. `CREDITCOACH_CACHE=off` turns everything off.

**How long, and why.**

| Layer | Time to live | Reason |
|---|---|---|
| Embedding | 7 days | Depends only on the model and the text, and the model is in the key. The limit only clears out questions nobody repeats. |
| Retrieval | 24 hours | The corpus fingerprint is in the key, so a corpus change takes effect at once. The limit clears unused entries. |
| Tool | 5 minutes | These are the user's credit figures. Five minutes keeps a burst of questions fast without serving figures that could be a data import behind. `scripts/data_import.py` also clears this layer and the answers. |
| Answer | 1 hour | Long enough for a user to come back to a question in one sitting. It is also re-checked against the live figures before every use (§3), so the limit is not what keeps it correct. |

**How large.** Measured in Redis after the evidence run: an embedding is about 8 KB as JSON, a retrieval result about 5 KB, a tool result about 1 KB, and an answer about 13 KB with its sources, plus 4 KB in the user's index. Answers are capped at 20 per user, oldest first, so with 15 users the answer layer tops out at about 5 MB. For a larger deployment, set Redis's `maxmemory` with the `allkeys-lru` policy; every entry can be recomputed, so eviction is always safe.

## 3. The answer cache: when a stored answer may be served

A cached answer can do harm in two ways: it can answer a different question, or rest on figures that have changed. A stored answer is served only if all of these hold.

| Check | How |
|---|---|
| **Same user** | Entries live under the signed-in user's keys. There is no lookup across users (guardrail rule S4). |
| **Same question** | Exact, same words, or model-confirmed (below). |
| **Same setup** | The system prompt, guardrail layer, models and corpus are the ones the answer was built with, and the user's stored goal and remembered facts are unchanged. Any change makes every older answer unusable. |
| **Same figures** | The user's score history and account summary are read (from the tool cache, at most 5 minutes old, or live) and compared with the ones the answer used. If they differ, the stored answer is deleted and a fresh one is written. |
| **Fresh** | Stored less than an hour ago. |

**Same question** is decided in three steps:

1. **Exact:** equal after lower-casing and removing punctuation.
2. **Same words:** embedding similarity of at least 0.90, and the same set of meaning-bearing words. Contractions, word order, tense, filler words and British spellings don't count: "My credit score dropped 20 points this month. Why?" matches "Why did my credit score drop 20 points this month?".
3. **Model-confirmed:** similarity of at least 0.90 with different words, and `SMALL_MODEL` agrees the stored answer fully answers the new question (about 1.4 s; any doubt or error is a no). `CREDITCOACH_CACHE_CONFIRM=off` removes this step.

**Embedding similarity alone is not safe.** Measured with the project's embedding model against "Why did my credit score drop 20 points this month?":

| Question | Similarity | Same question? |
|---|---|---|
| "Why has my credit score dropped 20 points this month?" | 0.988 | Yes |
| "What made my score fall by 20 points this month?" | 0.838 | Yes |
| "Why did my credit score drop 20 points **last** month?" | **0.996** | No |
| "Why did my credit score drop **40** points this month?" | 0.955 | No |
| "Why did my credit score **rise** 20 points this month?" | 0.939 | No |

No threshold separates the two groups. So two questions whose **numbers, negation or time words** differ are never matched, whatever their similarity and without asking the model. On 23 test pairs (10 rewordings, 13 look-alikes) this gave no wrong hit in two live runs; 8 of the 10 rewordings hit, and the other two scored below 0.90 and were answered afresh. A miss costs time. A wrong hit would give the user an answer about the wrong month.

**What is never stored or served from the answer cache:**

| Case | Why |
|---|---|
| The input rails flagged the question (personal identifiers, an attempt to switch the rules off or read the prompt) | Each must go through the guardrail layer on its own |
| The guardrail layer blocked the answer | A fixed safe message isn't an answer; the next try may do better |
| A tool call failed | The answer says "I can't pull your data right now", which must not outlive the failure |
| The answer saved or cleared the user's goal | Replaying it would skip the save |
| The fallback model wrote the answer | A degraded answer shouldn't be replayed for an hour |
| The question leans on the conversation ("this loan", "the other one", "instead"), once there is a conversation | Its answer depends on what was said before. A self-contained question is stored and served at any point in a chat, so repeating it later in the same chat hits (found in Task 25: the first version stored only a chat's opening question, and the repeat in the demo flow missed). The model did see the earlier turns when it wrote such an answer, so it may refer to them |

A stored answer already passed the output rails under the same guardrail configuration, so it isn't checked again on a hit. A reframed answer is stored as rewritten; the draft is never stored.

**Evaluations don't use the answer cache.** `pipeline.answer` reuses answers only when called with `use_cache=True`, which the chat UI does. The evaluation and evidence scripts leave it off, so they always measure the model. The other three layers stay on for them, except where a tool failure is injected on purpose.

## 4. The "live tool call" requirement

requirements.md §6 says every credit figure "must come from a live tool call, not assumed". Caching tool results and answers has to respect that:

- A cached tool result **is** a tool call's output, for the same user and the same arguments, at most 5 minutes old. Nothing is estimated or carried over from another user or another period. `ToolCall.cached` marks it, so the agent trace and the logs can show it.
- An answer is served from the cache only after the user's current figures are read and found equal to the ones in it.
- A tool error is never cached, so "I can't pull your latest data" lasts only as long as the failure does.

## 5. Evidence

**Measured improvement (Task 23,** [task-23-cache-latency.md](evidence/week-3/task-23-cache-latency.md)**).** Live, on a workload of 35 requests against Redis:

| | Uncached | Cached |
|---|---|---|
| Answer latency, median | 11.05 s | 0.009 s (a word-for-word repeat); 1.4 s (a rewording the small model confirms) |
| Model cost per answer | $0.0122 | $0 ($0.00008 for a confirmed rewording) |
| Hits | | 10 of 10 repeats, 10 of 10 rewordings, 0 of 5 look-alikes (0 wrong hits) |

The workload's overall hit rate was 57% (20 of 35), which cut its waiting time by 55% and its model cost by 57%. That rate belongs to the workload, where two thirds of the requests were deliberate repeats; real users repeat far less.

**Miss, then hit (Task 22).** 
[task-22-cache-log.md](evidence/week-3/task-22-cache-log.md), live against Redis: a question misses every layer and takes 11.0 s; the same question again hits and takes 0.01 s with no model call; a rewording hits; "last month" in place of "this month" misses on purpose; a different question reuses the user's cached lookups; another user shares nothing. `tests/test_cache.py` has 52 tests that need no Redis, API key or embedding model.

## 6. Open questions for team review

1. **Tool results for 5 minutes.** Is serving a user's figures from a 5-minute-old lookup acceptable under §6's "live tool call"? Proposal: yes, with §4's safeguards, and the dataset is a static snapshot. Setting `TTL["tool"]` to 0 would make every lookup live at a cost of about 1.8 s a question with the dataset in Neon.
2. **Answers for an hour.** Should the limit be shorter, or longer for the demo? Proposal: keep 1 hour; correctness comes from the checks in §3, not from the limit.
3. **Reworded questions.** Step 3 asks a model whether two questions are the same. It gave no wrong hit in testing, but it is a model. Task 23 saw none either (0 of 5 look-alikes matched). Proposal: keep it on, and review any wrong hit seen in the Week 4 evals.
4. **Evaluations and the cache.** Caching answers in eval runs would cut their cost, but a run would then partly measure the cache. Proposal: keep evals uncached, and reconsider with the Task 27 harness.
5. **One Redis each, or one shared.** Each teammate runs a local Redis today. A shared Redis would let a demo machine reuse answers warmed elsewhere, at the cost of a secret to manage. Proposal: local for now.
6. **Query router.** Sending simple questions to a cheaper model would cut the cost of a cache miss. Not in tasks.md. Task 23 measured a miss at $0.0122 and 11 s; proposal: the team decides whether that is worth a router.

## 7. Sign-off

| Member | Reviewed | Date |
|---|---|---|
| Aman | [ ] | |
| Anil | [ ] | |
| Sudip | [ ] | |
