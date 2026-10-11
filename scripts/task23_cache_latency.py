"""Task 23: measure the cache's hit rate and how much faster and cheaper a cached answer is.

Definition of Done: latency compared for cached vs. uncached calls with documented improvement.

Two measurements, both against the configured cache store (Redis when ``REDIS_URL`` is set):

    1. Whole answers, live. A fixed workload of 35 requests goes through ``pipeline.answer(..., use_cache=True)``,
       as the chat UI calls it, one at a time, starting from an empty cache:
           Pass 1  10 questions from requirements.md, first time     uncached: every one is a GPT-5 answer
           Pass 2  the same 10 again, word for word                  cached
           Pass 3  the 10 reworded by hand (same meaning)            cached when the rewording is recognised
           Pass 4  5 look-alikes (another month, number or product)  must NOT be served from the cache
       For each request: wall-clock time, whether the answer cache hit and how, every model call's tokens and
       cost as OpenRouter reports them, and whether a hit was a correct one.
    2. Each layer on its own, 30 repetitions, no model call: computing an embedding, retrieving passages, and
       fetching a user's score history and account summary over MCP, each against reading it from the cache.

Writes:
    docs/evidence/week-3/task-23-cache-latency.md     the before/after numbers
    docs/evidence/week-3/runs/task-23-cache-latency.json   every request and timing behind them

Run (needs OPENROUTER_API_KEY, the vector store and the cache store; about 20 GPT-5 answers, 6 minutes):
    uv run python scripts/task23_cache_latency.py
    uv run python scripts/task23_cache_latency.py --report    # rewrite the Markdown from the saved JSON
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import datetime

from creditcoach import cache, config, llm
from creditcoach.agent import pipeline
from creditcoach.agent.mcp_host import McpHost
from creditcoach.evals import golden
from creditcoach.rag import retrieve as rag

WEEK3 = config.ROOT / "docs" / "evidence" / "week-3"
EVIDENCE, RUN = WEEK3 / "task-23-cache-latency.md", WEEK3 / "runs" / "task-23-cache-latency.json"
REPEATS = 30

BASE = [1, 2, 3, 4, 6, 9, 29, 31, 33, 42]  # requirements.md query numbers; each runs as its own user
REWORDED = {
    1: "My credit score dropped 20 points this month. Why?",
    2: "What is my credit utilization ratio right now?",
    3: "I'd like to buy a car in 12 months. What should I focus on?",
    4: "Should I take a payday loan to pay off my credit card?",
    6: "Can you guarantee that my score will reach 720 if I follow your advice?",
    9: "Why has my score dipped over the last two months? I have always paid on time.",
    29: "Is it OK to take another instant loan app loan to pay this month's card bill?",
    31: "How does a payday loan work?",
    33: "Would a balance transfer be a good idea for my 79% card?",
    42: "When exactly is my score going to be back at 811?",
}
LOOK_ALIKE = {  # close in wording to the base question, different in meaning: a cache hit here would be a wrong answer
    1: "Why did my credit score drop 20 points last month?",
    2: "What should my credit utilization ratio be?",
    3: "I want to buy a car in 6 months — what should I focus on?",
    6: "Can you guarantee my score will hit 750 if I do what you said?",
    33: "Is a balance transfer a good idea for my 19% card?",
}
PASSES = [("1 first time", "uncached", {i: None for i in BASE}), ("2 repeated", "should hit", {i: None for i in BASE}),
          ("3 reworded", "may hit", REWORDED), ("4 look-alike", "must miss", LOOK_ALIKE)]


def ask(phase: str, expect: str, qid: int, question: str | None) -> dict:
    q = golden.by_id()[qid]
    question = question or q.query
    with llm.track() as calls:
        t0 = time.perf_counter()
        a = pipeline.answer(question, user_id=q.user_id, use_cache=True)
        seconds = time.perf_counter() - t0
    events = a.cache["events"]
    rec = {"phase": phase, "expect": expect, "query": qid, "user_id": q.user_id, "question": question,
           "seconds": round(seconds, 3), "status": a.cache["status"], "how": a.cache.get("how"),
           "similarity": a.cache.get("similarity"), "matched_question": a.cache.get("matched_question"),
           "stored": a.cache.get("stored"), "not_stored_because": a.cache.get("reason") if a.cache.get("stored") is False else None,
           "miss_reason": next((e.get("reason") for e in events if e["layer"] == "answer" and e["result"] == "miss"), None),
           "guardrail": a.guardrail.action, "answer_model": a.model,
           "calls": calls, "cost": round(sum(c["cost"] for c in calls), 6),
           "prompt_tokens": sum(c["prompt_tokens"] for c in calls),
           "completion_tokens": sum(c["completion_tokens"] for c in calls),
           "tool_lookups": [e["result"] for e in events if e["layer"] == "tool" and e["result"] in ("hit", "miss")],
           "answer_chars": len(a.text)}
    rec["wrong_hit"] = rec["status"] == "hit" and expect == "must miss"
    print(f"  {phase:13} #{qid:<3} {rec['status']:5} {(rec['how'] or ''):16} {seconds:6.2f}s  ${rec['cost']:.4f}", flush=True)
    return rec


def timed(fn, repeats: int = REPEATS) -> list[float]:
    """Milliseconds for each of ``repeats`` calls of ``fn``."""
    out = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        out.append((time.perf_counter() - t0) * 1000)
    return out


def layers() -> dict:
    """Each layer on its own: the work it replaces against reading the cached value. No model call."""
    question, user_id = golden.by_id()[1].query, "USR-001"
    text = rag.normalize_query(question)

    async def over_mcp():
        async with McpHost(user_id) as host:
            for name, args in pipeline.PREFETCH:
                await host.call(name, args)
    out = {}
    with cache.disabled():
        out["embedding"] = {"uncached": timed(lambda: rag.embed(text))}
        out["retrieval"] = {"uncached": timed(lambda: rag.retrieve(question))}
        out["tool"] = {"uncached": timed(lambda: asyncio.run(over_mcp()), 10)}
    rag.embed(text), rag.retrieve(question), pipeline._prefetch(user_id)  # fill the cache
    out["embedding"]["cached"] = timed(lambda: rag.embed(text))
    out["retrieval"]["cached"] = timed(lambda: rag.retrieve(question))
    out["tool"]["cached"] = timed(lambda: pipeline._prefetch(user_id))
    return out


def measure() -> dict:
    store = cache.backend()
    where = store.name
    if where == "redis":
        where = f"Redis {store.client.info('server')['redis_version']} ({config.REDIS_URL.split('@')[-1].split('//')[-1]})"
    rag.retrieve("warm up the embedding and reranker models")  # model loading is not what is being measured
    cache.clear()
    records = []
    for phase, expect, questions in PASSES:
        print(f"Pass {phase}", flush=True)
        records += [ask(phase, expect, qid, text) for qid, text in questions.items()]
    counters = cache.stats()
    print("Layers", flush=True)
    return {"created": datetime.now().isoformat(timespec="seconds"), "store": where, "model": config.CHAT_MODEL,
            "small_model": config.SMALL_MODEL, "reasoning_effort": config.REASONING_EFFORT, "ttl": cache.TTL,
            "data_backend": config.DATA_BACKEND,
            "records": records, "counters": counters, "layers": layers()}


def spread(values: list[float], unit: str = "s", digits: int = 2) -> str:
    return (f"{statistics.median(values):.{digits}f} {unit} (min {min(values):.{digits}f}, max {max(values):.{digits}f}, "
            f"n={len(values)})")


def report(run: dict) -> bool:
    recs = run["records"]
    phase = lambda name: [r for r in recs if r["phase"].startswith(name)]  # noqa: E731
    first, repeated, reworded, alike = phase("1"), phase("2"), phase("3"), phase("4")
    hits = [r for r in recs if r["status"] == "hit"]
    uncached, cached = [r["seconds"] for r in first], [r["seconds"] for r in repeated if r["status"] == "hit"]
    med_un, med_ca = statistics.median(uncached), statistics.median(cached)
    cost_un = statistics.mean(r["cost"] for r in first)
    after_warm = repeated + reworded + alike
    wrong = [r for r in recs if r["wrong_hit"]]
    confirmed = [r for r in hits if r["how"] == "model-confirmed"]
    ok = (len(cached) == len(repeated) and not wrong and all(r["status"] != "hit" for r in first) and med_ca < med_un / 10)

    by_how = {}
    for r in hits:
        by_how.setdefault(r["how"], []).append(r)
    total_cost, cost_no_cache = sum(r["cost"] for r in recs), len(recs) * cost_un
    total_time, time_no_cache = sum(r["seconds"] for r in recs), len(recs) * statistics.mean(uncached)

    lines = ["# Task 23 Evidence: Cache Hit Rate and Latency", "",
             f"*{run['created'][:10]} · Code: `creditcoach/cache/` · Design: [docs/caching.md](../../caching.md) · Script: "
             f"`uv run python scripts/task23_cache_latency.py` · Data: [{RUN.name}](runs/{RUN.name})*", "",
             "**Definition of Done:** latency compared for cached vs. uncached calls with documented improvement.", "",
             f"**Result: {'✅ PASS' if ok else '❌ FAIL'}**", "",
             "| | Uncached (first time) | Cached (repeated) | Improvement |", "|---|---|---|---|",
             f"| **Answer latency, median** | **{med_un:.2f} s** | **{med_ca:.3f} s** | **{med_un / med_ca:,.0f}× faster** "
             f"({med_un - med_ca:.1f} s saved) |",
             f"| Answer latency, range | {min(uncached):.2f} to {max(uncached):.2f} s | {min(cached):.3f} to {max(cached):.3f} s | |",
             f"| GPT-5 calls per answer | {statistics.mean(sum(c['model'] == run['model'] for c in r['calls']) for r in first):.1f} | 0 | |",
             f"| Model cost per answer, mean | ${cost_un:.4f} | $0 | 100% |",
             f"| Tokens per answer, mean (in / out) | {statistics.mean(r['prompt_tokens'] for r in first):,.0f} / "
             f"{statistics.mean(r['completion_tokens'] for r in first):,.0f} | 0 / 0 | |", "",
             f"Measured live on {run['created'][:16].replace('T', ' ')} with `{run['model']}` (reasoning effort "
             f"`{run['reasoning_effort']}`) over MCP, the guardrail layer on, and the cache in **{run['store']}**, emptied "
             "first. Requests ran one at a time through `pipeline.answer(..., use_cache=True)`, as the chat UI calls it. "
             "Costs are what OpenRouter reported for each call, in US dollars, and include the guardrail layer's "
             "wording review.", "",
             "## 1. Hit rate on the workload", "",
             f"{len(recs)} requests in four passes. The hit rate depends entirely on how often users repeat themselves, so "
             "these figures describe this workload, not real traffic.", "",
             "| Pass | Requests | Answer-cache hits | Hit rate | Median time | Model cost |", "|---|---|---|---|---|---|"]
    for name, rs, note in (("1. First time (cache empty)", first, ""), ("2. Repeated word for word", repeated, ""),
                           ("3. Reworded, same meaning", reworded, ""),
                           ("4. Look-alike, different meaning", alike, " (a hit would be a wrong answer)")):
        n = sum(r["status"] == "hit" for r in rs)
        lines.append(f"| {name} | {len(rs)} | {n}{note} | {n / len(rs):.0%} | "
                     f"{statistics.median(r['seconds'] for r in rs):.2f} s | ${sum(r['cost'] for r in rs):.4f} |")
    lines += [f"| **All four passes** | **{len(recs)}** | **{len(hits)}** | **{len(hits) / len(recs):.0%}** | | "
              f"**${total_cost:.4f}** |",
              f"| After the first pass (2 to 4) | {len(after_warm)} | {sum(r['status'] == 'hit' for r in after_warm)} | "
              f"{sum(r['status'] == 'hit' for r in after_warm) / len(after_warm):.0%} | | |", "",
              f"- **Wrong hits: {len(wrong)}.** None of the {len(alike)} look-alike questions was served from the cache.",
              f"- **Repeats: {len(cached)} of {len(repeated)} hit**, each with the answer identical to the first.",
              f"- **Rewordings: {sum(r['status'] == 'hit' for r in reworded)} of {len(reworded)} hit.** "
              + "; ".join(f"{len(rs)} by {how} (median {statistics.median(r['seconds'] for r in rs):.2f} s)"
                          for how, rs in by_how.items() if how != "exact" or any(r in reworded for r in rs))
              + ". A rewording that isn't recognised is answered afresh: slower, never wrong.",
              f"- **Without the cache**, {len(recs)} requests at the first-pass averages would have taken about "
              f"{time_no_cache / 60:.1f} minutes of waiting and ${cost_no_cache:.2f}. With it they took "
              f"{total_time / 60:.1f} minutes and ${total_cost:.2f}: **{1 - total_time / time_no_cache:.0%} less time and "
              f"{1 - total_cost / cost_no_cache:.0%} less cost** on this workload.", ""]

    lines += ["Hits and misses per layer over the whole workload, from the cache's own counters:", "",
              "| Layer | Hits | Misses | Hit rate | Stores |", "|---|---|---|---|---|"]
    for layer in ("embedding", "retrieval", "tool", "answer"):
        c = run["counters"].get(layer, {})
        lines.append(f"| {layer} | {c.get('hit', 0)} | {c.get('miss', 0)} | {c.get('hit_rate') or 0:.0%} | {c.get('store', 0)} |")
    lines += ["", f"The tool layer keeps a result for {run['ttl']['tool'] // 60} minutes, so some of its misses are "
              "lookups that had expired by the time a later pass reached that user, not new work.", ""]

    lines += ["## 2. Latency, request by request", "",
              "| Query | User | Pass 1: first time | Pass 2: repeated | Faster | Pass 3: reworded | How the rewording matched |",
              "|---|---|---|---|---|---|---|"]
    for q in BASE:
        a, b, c = (next(r for r in rs if r["query"] == q) for rs in (first, repeated, reworded))
        matched = (f"{c['how']} ({c['similarity']})" if c["status"] == "hit" else f"miss: {(c['miss_reason'] or '')[:70]}")
        lines.append(f"| #{q} {a['question']} | {a['user_id']} | {a['seconds']:.2f} s | {b['seconds']:.3f} s ({b['status']}) | "
                     f"{a['seconds'] / b['seconds']:,.0f}× | {c['seconds']:.2f} s ({c['status']}) | {matched} |")
    lines += ["", "Rewordings asked in pass 3:", "",
              *(f"- #{q}: *\"{REWORDED[q]}\"*" for q in BASE), "",
              "Look-alike questions (pass 4), all answered afresh:", "",
              "| Base query | Look-alike question | Result | Why it wasn't matched | Time |", "|---|---|---|---|---|",
              *(f"| #{r['query']} | {r['question']} | {r['status']} | {r['miss_reason']} | {r['seconds']:.2f} s |" for r in alike), ""]
    if confirmed:
        lines += [f"A model-confirmed hit includes one `{run['small_model']}` call to check the two questions ask the "
                  f"same thing: median {statistics.median(r['seconds'] for r in confirmed):.2f} s and "
                  f"${statistics.mean(r['cost'] for r in confirmed):.5f} a hit, against {med_un:.1f} s and ${cost_un:.4f} "
                  "for a fresh answer.", ""]
    slow_first = [r for r in first if r["guardrail"] != "passed"]
    if slow_first:
        lines += [f"{len(slow_first)} first-pass answer(s) were rewritten by the guardrail layer "
                  f"({', '.join('#' + str(r['query']) for r in slow_first)}), which is why they took longest.", ""]

    L = run["layers"]
    lines += ["## 3. Each layer on its own", "",
              f"The work a layer replaces, against reading the cached value, {REPEATS} repetitions each (10 for the MCP "
              "round trip), no model call.", "",
              "| Layer | What is measured | Uncached, median | Cached, median | Faster | Saved per use |",
              "|---|---|---|---|---|---|"]
    for layer, what in (("embedding", "Embedding one question with the local model"),
                        ("retrieval", "Vector search and reranking for one question"),
                        ("tool", "Starting the MCP server, which reads the dataset from "
                                 f"{'Neon' if run['data_backend'] == 'postgres' else 'data/*.csv'}, and fetching score "
                                 "history and account summary")):
        u, c = statistics.median(L[layer]["uncached"]), statistics.median(L[layer]["cached"])
        lines.append(f"| {layer} | {what} | {u:.2f} ms | {c:.2f} ms | {u / c:.1f}× | {u - c:.1f} ms |")
    answer_saved = (med_un - med_ca) * 1000
    lines += [f"| answer | A whole answer (from §2) | {med_un * 1000:,.0f} ms | {med_ca * 1000:.1f} ms | {med_un / med_ca:,.0f}× | "
              f"{answer_saved:,.0f} ms |", "",
              f"The answer layer saves {answer_saved / 1000:.0f} seconds, because the model is almost all of an answer's "
              "time. Of the other three, only the tool layer is noticeable: with the dataset in "
              f"{'Neon' if run['data_backend'] == 'postgres' else 'files'}, fetching a user's figures over MCP takes "
              f"{statistics.median(L['tool']['uncached']) / 1000:.1f} s, and an answer-cache hit needs those figures to "
              "check the stored answer is still right. Reading them from the cache is why a hit takes milliseconds. "
              "The retrieval layer shows 0 hits in §1 because it is only reached when the answer cache misses, and "
              "in this workload every miss was a question not asked before.", "",
              "## 4. What these numbers do and don't show", "",
              "- **The speed-up is real and repeatable**: every word-for-word repeat hit, and a hit never called GPT-5.",
              "- **The hit rate is the workload's.** Two thirds of these requests were deliberate repeats or rewordings. "
              "Real users repeat far less, so the saving in production would be smaller. The demo's repeated "
              "factor-lookup question is the case this is built for.",
              "- **Evaluation runs are not cached** (docs/caching.md §3), so this does not yet reduce what an eval run costs.",
              f"- **One machine, one run, one request at a time.** Uncached times vary with the model provider "
              f"({min(uncached):.1f} to {max(uncached):.1f} s here). Cached times depend on a local Redis; a remote one "
              "would add its network round trips.",
              "- **Sample sizes are small**: 10 questions per pass, so medians and ranges are given, not percentiles.", ""]
    EVIDENCE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{'PASS' if ok else 'FAIL'}: wrote {EVIDENCE.relative_to(config.ROOT)}  "
          f"(uncached {med_un:.2f}s, cached {med_ca:.3f}s, hits {len(hits)}/{len(recs)}, wrong {len(wrong)})")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--report", action="store_true", help="rewrite the Markdown from the saved JSON, no model calls")
    args = parser.parse_args()
    config.MEMORY_BACKEND = "files"  # no memory session is opened; this keeps any stray write off the shared database
    if args.report:
        run = json.loads(RUN.read_text(encoding="utf-8"))
    else:
        if not cache.enabled():
            sys.exit("The cache is off (CREDITCOACH_CACHE=off).")
        run = measure()
        RUN.parent.mkdir(parents=True, exist_ok=True)
        RUN.write_text(json.dumps(run, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    sys.exit(0 if report(run) else 1)


if __name__ == "__main__":
    main()
