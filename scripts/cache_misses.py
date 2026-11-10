"""List the answer cache's real misses as question pairs to judge, for the benchmark in task22_confirm_band.py.

Every miss of the semantic answer cache records, on its ``cache.answer`` span, why it missed, how similar the closest
stored question was, and (since 2026-11-10) that question (``cache.closest``). This reads the chat app's misses from
Langfuse for the last few days and prints each as a pair: the user's earlier question and the one that missed. Mark
each one a rewording (should have hit) or a look-alike (rightly missed), add it to ``REWORDINGS`` or ``LOOK_ALIKES``
in ``scripts/task22_confirm_band.py``, then re-run that script and ``scripts/task22_cross_encoder.py``.

The questions are users' own words: paste only the pairs you need into the benchmark, never this whole output.
Misses from before 2026-11-10 have no closest question and are left out.

Run (needs the Langfuse keys in .env; read-only):
    uv run python scripts/cache_misses.py            # the last 7 days, similarity 0.5 and up
    uv run python scripts/cache_misses.py 30 0.6     # the last 30 days, similarity 0.6 and up
"""

import sys
from datetime import UTC, datetime, timedelta

from creditcoach.app import dashboard


def misses(days: int, lowest: float) -> list[dict]:
    """The chat app's answer-cache misses in the last ``days`` days at ``lowest`` similarity or above, newest first."""
    since = datetime.now(UTC) - timedelta(days=days)
    spans = {}
    for name in ("cache.answer", "creditcoach.answer"):
        cursor = None
        for _ in range(dashboard.MAX_PAGES):
            page = dashboard._langfuse_get("/api/public/v2/observations", limit=1000, cursor=cursor, name=name,
                                           fields="core,basic,metadata",
                                           fromStartTime=since.strftime("%Y-%m-%dT%H:%M:%SZ"))
            for o in page.get("data", []):
                spans.setdefault(o.get("traceId"), {})[name] = dashboard._from_observation(o)
            cursor = (page.get("meta") or {}).get("cursor")
            if not cursor or not page.get("data"):
                break
    found = []
    for got in spans.values():
        lookup, answer = got.get("cache.answer"), got.get("creditcoach.answer")
        if not (lookup and answer):
            continue
        a, c = answer["attributes"], lookup["attributes"]
        real = dashboard.run_of(set(a.get("langfuse.trace.tags") or []), answer.get("env", "")) is None
        similarity = dashboard._number(c.get("cache.similarity"))
        if real and c.get("cache.result") == "miss" and c.get("cache.closest") and similarity >= lowest:
            found.append({"when": answer["start"][:16].replace("T", " "), "user": a.get("user.id"),
                          "similarity": similarity, "reason": c.get("cache.reason", ""),
                          "stored": c["cache.closest"], "asked": a.get("question", "")})
    return sorted(found, key=lambda m: m["when"], reverse=True)


def main() -> None:
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    lowest = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
    found = misses(days, lowest)
    print(f"{len(found)} misses in the last {days} days at similarity {lowest} or above\n")
    print("| When (UTC) | User | Similarity | Why it missed | Earlier question | Question that missed | Same? |")
    print("|---|---|---|---|---|---|---|")
    for m in found:
        print(f"| {m['when']} | {m['user']} | {m['similarity']:.3f} | {m['reason']} | {m['stored']} | {m['asked']} | |")


if __name__ == "__main__":
    main()
