"""Task 22: ask the same question twice, live, and write the cache log (a miss, then a hit) as evidence.

Definition of Done: repeated identical queries hit the cache instead of re-querying.

Starting from an empty cache, six live questions go through ``agent.pipeline.answer`` as the chat UI calls it
(``use_cache=True``), and every cache event is captured from the ``creditcoach.cache`` logger:

    1. A question, first time            every layer misses and stores; GPT-5 answers.
    2. The same question again           embedding hit, answer hit: no retrieval, no MCP server, no model call.
    3. The question reworded             answer hit through the "same words" match.
    4. A look-alike ("last month")       answer miss, on purpose: a fresh answer; the tool lookups still hit.
    5. A different question, same user   answer miss; the score and account lookups are served from the cache.
    6. The first question, another user  answer miss: nothing is shared between users.

Writes:
    docs/evidence/week-3/task-22-cache-log.md

Run (needs OPENROUTER_API_KEY and the vector store; 4 GPT-5 answers; uses REDIS_URL if set, else memory):
    uv run python scripts/task22_cache_log.py
"""

import json
import sys
import time
from datetime import date

from creditcoach import cache, config
from creditcoach.agent import pipeline
from creditcoach.rag import retrieve as rag

EVIDENCE = config.ROOT / "docs" / "evidence" / "week-3" / "task-22-cache-log.md"
DROP = "Why did my credit score drop 20 points this month?"
STEPS = [  # (title, user, question, expected answer-cache status, GPT-5 expected to run)
    ("A question, first time", "USR-001", DROP, "miss", True),
    ("The same question again", "USR-001", DROP, "hit", False),
    ("The question reworded", "USR-001", "My credit score dropped 20 points this month. Why?", "hit", False),
    ("A look-alike question", "USR-001", "Why did my credit score drop 20 points last month?", "miss", True),
    ("A different question, same user", "USR-001", "What's my current credit utilization ratio?", "miss", True),
    ("The first question, another user", "USR-003", DROP, "miss", True),
]
LAYERS = ("embedding", "answer", "retrieval", "tool")


def summary(events: list[dict], layer: str) -> str:
    """What one layer did for one question, for example "1 miss, 1 store" or "hit (exact)"."""
    mine = [e for e in events if e["layer"] == layer]
    if not mine:
        return "not used"
    counts: dict[str, int] = {}
    for e in mine:
        counts[e["result"]] = counts.get(e["result"], 0) + 1
    return ", ".join(f"{n} {result}" for result, n in counts.items())


def main() -> None:
    config.MEMORY_BACKEND = "files"  # no memory session is opened; this keeps any stray write off the shared database
    if not cache.enabled():
        sys.exit("The cache is off (CREDITCOACH_CACHE=off).")
    store = cache.backend()
    where = store.name
    if where == "redis":
        info = store.client.info("server")
        where = f"Redis {info['redis_version']} ({config.REDIS_URL.split('@')[-1].split('//')[-1]})"
    else:
        where = "this process's memory (REDIS_URL is not set)"
    removed = cache.clear()
    rag.retrieve("warm up the embedding and reranker models")  # model loading is not what is being measured
    cache.clear()
    models = []
    real = pipeline.chat_with_tools

    def counting(messages, tools, model=None):
        models.append(1)
        return real(messages, tools, model)
    pipeline.chat_with_tools = counting

    rows, details, ok = [], [], True
    for n, (title, user_id, question, want, want_model) in enumerate(STEPS, 1):
        print(f"{n}. {title}", flush=True)
        before, t0 = len(models), time.perf_counter()
        a = pipeline.answer(question, user_id=user_id, use_cache=True)
        seconds, called = time.perf_counter() - t0, len(models) > before
        events = a.cache["events"]
        good = a.cache["status"] == want and called == want_model
        ok = ok and good
        how = f" ({a.cache['how']})" if a.cache["status"] == "hit" else ""
        rows.append(f"| {n} | {title} | {user_id} | {question} | **{a.cache['status']}**{how} | "
                    + " | ".join(summary(events, layer) for layer in ("embedding", "retrieval", "tool"))
                    + f" | {'yes' if called else '**no**'} | {seconds:.2f} s | {'✅' if good else '❌'} |")
        details += [f"### {n}. {title}", "", f"Asked as {user_id}: *\"{question}\"*", "", "```json",
                    *(json.dumps({k: v for k, v in e.items() if k != "event"}, ensure_ascii=False) for e in events),
                    "```", ""]
        if a.cache["status"] == "hit":
            details += [f"Served the answer stored for *\"{a.cache['matched_question']}\"* ({a.cache['how']}, "
                        f"similarity {a.cache['similarity']}, stored {a.cache['age_seconds']} s earlier), after checking "
                        f"the user's figures are unchanged. The original took {a.cache['saved_seconds'] + seconds:.1f} s.", ""]
        elif n == 4:
            reason = next(e["reason"] for e in events if e["layer"] == "answer" and e["result"] == "miss")
            details += [f"Not served from the cache: {reason}. A stored answer about this month would have been wrong "
                        "for last month.", ""]
        if n <= 2:
            details += ["Answer shown to the user" + (" (identical to the first)" if n == 2 else "") + ":", "",
                        *[f"> {line}" if line else ">" for line in a.text.splitlines()], ""]
            if n == 1:
                first = a.text
            else:
                ok = ok and a.text == first
    pipeline.chat_with_tools = real
    stats = cache.stats()
    kept = {layer: len(store.keys(f"cc:{cache.SCHEMA}:{layer}:")) for layer in LAYERS}

    lines = ["# Task 22 Evidence: Cache Miss, Then Hit", "",
             f"*{date.today().isoformat()} · Code: `creditcoach/cache/`, `creditcoach/rag/retrieve.py`, "
             "`creditcoach/agent/mcp_host.py`, `creditcoach/agent/pipeline.py` · Design: [docs/caching.md](../../caching.md) "
             "· Tests: `tests/test_cache.py` · Script: `uv run python scripts/task22_cache_log.py`*", "",
             "**Definition of Done:** repeated identical queries hit the cache instead of re-querying.", "",
             f"**Result: {'✅ PASS' if ok else '❌ FAIL'}**", "",
             f"Cache store: **{where}**. It was emptied before the run ({removed} keys removed). Every answer is live, "
             f"from `{config.CHAT_MODEL}` over MCP, through `pipeline.answer(..., use_cache=True)` as the chat UI calls it.", "",
             "| # | Step | User | Question | Answer cache | Embedding | Retrieval | Tool lookups | GPT-5 called | Time | As expected |",
             "|---|---|---|---|---|---|---|---|---|---|---|", *rows, "",
             "Read the table as: question 1 misses every layer and stores what it computed. Question 2, the same "
             "question, hits the embedding cache and then the answer cache, so nothing is retrieved, no MCP server "
             "starts and GPT-5 is not called. Question 3 is a rewording and hits too. Question 4 looks almost the "
             "same to the embedding model but asks about another month, so it is answered afresh. Question 5 is new, "
             "but the user's score history and account summary come from the cache. Question 6 shows that another "
             "user shares nothing.", "",
             "## Cache log, question by question", "",
             "Each line is one entry from the `creditcoach.cache` logger, in order.", "", *details,
             "## Counters and what is stored afterwards", "",
             "| Layer | Hits | Misses | Stores | Hit rate | Keys now | Time to live |", "|---|---|---|---|---|---|---|",
             *(f"| {layer} | {stats.get(layer, {}).get('hit', 0)} | {stats.get(layer, {}).get('miss', 0)} | "
               f"{stats.get(layer, {}).get('store', 0)} | {stats.get(layer, {}).get('hit_rate')} | {kept[layer]} | "
               f"{cache.TTL[layer]:,} s |" for layer in LAYERS), "",
             "Hit rates over six scripted questions only show that the counters work. Task 23 measures the hit rate "
             "and the latency improvement properly.", ""]
    EVIDENCE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{'PASS' if ok else 'FAIL'}: wrote {EVIDENCE.relative_to(config.ROOT)} (store: {where})")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
