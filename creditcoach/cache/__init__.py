"""CreditCoach's cache (Task 22): repeated lookups are served from Redis instead of being computed again.

Four layers, each with its own key, time to live and rule for what may be stored. The design, with the reasons,
is in ``docs/caching.md``.

    Layer        What is cached                                  Key                                      TTL
    embedding    a question's embedding vector                   embedding model + text                   7 days
    retrieval    the passages retrieved for a question           corpus + models + question + options     24 hours
    tool         a successful score-history or account lookup    user + tool + arguments + data backend   5 minutes
    answer       a finished, guardrail-checked answer            user + question (exact or same meaning)  1 hour

The first three are exact-match ("standard") caches of deterministic work. The answer layer is the semantic
cache (``creditcoach.cache.answers``): the same user asking the same question again gets the stored answer
without a model call, after the user's live figures are checked to be unchanged.

Everything goes through ``get`` and ``put`` here, which
    * do nothing when the cache is off (``CREDITCOACH_CACHE=off``; tests turn it off by default),
    * never raise: a Redis error is logged, counted, and treated as a miss, and Redis is then left alone for
      ``BREAK_SECONDS`` so a dead server doesn't slow every lookup,
    * log one JSON line per lookup on the ``creditcoach.cache`` logger,
    * count hits, misses and stores per layer (``stats``) for Task 23,
    * and record the lookup in the list opened by ``collect()``, so one answer can report what it used.

Example:
    >>> from creditcoach import cache
    >>> with cache.collect() as events:
    ...     key = cache.key("embedding", "all-MiniLM-L6-v2", "why did my score drop?")
    ...     cache.get("embedding", key)            # None: a miss
    ...     cache.put("embedding", key, [0.1, 0.2])
    ...     cache.get("embedding", key)            # [0.1, 0.2]: a hit
    >>> [(e["layer"], e["result"]) for e in events]
    [('embedding', 'miss'), ('embedding', 'store'), ('embedding', 'hit')]
"""

import contextvars
import hashlib
import json
import logging
import time
from contextlib import contextmanager

from creditcoach import config
from creditcoach.cache.backend import MemoryBackend, RedisBackend

log = logging.getLogger("creditcoach.cache")

SCHEMA = "1"  # part of every key: raise it to abandon everything cached by older code
TTL = {"embedding": 7 * 24 * 3600, "retrieval": 24 * 3600, "tool": 300, "answer": 3600}
"""Seconds each layer keeps a value. Embeddings depend only on the model and the text. Retrieval results also
depend on the corpus, which is in the key, so the TTL only bounds how long unused entries stay. Tool results are
the user's credit figures: five minutes keeps a burst of questions fast without serving figures that could be an
import behind. Answers are kept for an hour and are also re-checked against the live figures before use."""
BREAK_SECONDS = 30.0

_backend = None
_broken_until = 0.0
_events: contextvars.ContextVar[list | None] = contextvars.ContextVar("cache_events", default=None)


def enabled() -> bool:
    return config.CACHE != "off"


def backend():
    """The store in use: Redis if ``REDIS_URL`` is set, else this process's memory. Built on first use."""
    global _backend
    if _backend is None:
        _backend = RedisBackend(config.REDIS_URL) if config.REDIS_URL else MemoryBackend()
    return _backend


def use(store) -> None:
    """Replace the store (tests, and scripts that want a fresh one). ``None`` rebuilds it from the config."""
    global _backend, _broken_until
    _backend, _broken_until = store, 0.0


def key(layer: str, *parts, scope: str = "") -> str:
    """A cache key: ``cc:<schema>:<layer>:[<scope>:]<digest of parts>``. ``scope`` is a user id for per-user layers,
    so one user's entries can be listed or cleared and can never be read under another user's key."""
    digest = hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:32]
    return f"cc:{SCHEMA}:{layer}:{scope + ':' if scope else ''}{digest}"


def _note(layer: str, result: str, key_: str, count: bool = True, **extra) -> None:
    entry = {"event": "cache", "layer": layer, "result": result, "key": key_, **extra}
    log.info(json.dumps(entry, ensure_ascii=False))
    events = _events.get()
    if events is not None:
        events.append(entry)
    if count:
        _try(lambda: backend().incr(f"cc:{SCHEMA}:stats:{layer}:{result}"), layer, "stats", quiet=True)


def _try(action, layer: str, key_: str, quiet: bool = False):
    """Run one backend call. On any error: log it, stop using the backend for a while, and return None."""
    global _broken_until
    if time.monotonic() < _broken_until:
        return None
    try:
        return action()
    except Exception as exc:
        _broken_until = time.monotonic() + BREAK_SECONDS
        log.warning("Cache backend %s failed (%s: %s); answering without it for %d s",
                    backend().name, type(exc).__name__, exc, BREAK_SECONDS)
        if not quiet:
            _note(layer, "error", key_, count=False, error=type(exc).__name__)
        return None


def get(layer: str, key_: str, **extra):
    """The cached value for ``key_``, or None. Logs and counts a hit or a miss."""
    if not enabled():
        return None
    start = time.perf_counter()
    raw = _try(lambda: backend().get(key_), layer, key_)
    value = json.loads(raw) if raw is not None else None
    _note(layer, "hit" if value is not None else "miss", key_, ms=round((time.perf_counter() - start) * 1000, 2), **extra)
    return value


def put(layer: str, key_: str, value, ttl: int | None = None, **extra) -> None:
    """Store a JSON-serialisable value for the layer's time to live."""
    if not enabled():
        return
    ttl = ttl or TTL[layer]
    _try(lambda: backend().set(key_, json.dumps(value, ensure_ascii=False), ttl), layer, key_)
    _note(layer, "store", key_, ttl=ttl, **extra)


def skip(layer: str, reason: str, **extra) -> None:
    """Record that a layer was deliberately not used (for example an answer that must not be cached)."""
    if enabled():
        _note(layer, "skip", "", reason=reason, **extra)


def delete(*keys: str) -> None:
    if enabled() and keys:
        _try(lambda: backend().delete(*keys), "cache", keys[0])


@contextmanager
def collect():
    """Collect every cache event of the enclosed code (one question) in a list."""
    events: list[dict] = []
    token = _events.set(events)
    try:
        yield events
    finally:
        _events.reset(token)


@contextmanager
def disabled():
    """Turn the cache off for the enclosed code (evaluations that inject a tool failure, uncached timings)."""
    saved, config.CACHE = config.CACHE, "off"
    try:
        yield
    finally:
        config.CACHE = saved


def stats() -> dict[str, dict[str, int]]:
    """Hits, misses and stores per layer since the counters were last cleared, with the hit rate."""
    out: dict[str, dict] = {}
    prefix = f"cc:{SCHEMA}:stats:"
    for k in _try(lambda: backend().keys(prefix), "cache", prefix) or []:
        layer, result = k[len(prefix):].split(":")
        out.setdefault(layer, {})[result] = int(backend().get(k) or 0)
    for counts in out.values():
        looked = counts.get("hit", 0) + counts.get("miss", 0)
        counts["hit_rate"] = round(counts.get("hit", 0) / looked, 3) if looked else None
    return out


def clear(layer: str = "", scope: str = "") -> int:
    """Delete cached entries: everything, one layer, or one user's entries in a layer. Returns how many."""
    prefix = f"cc:{SCHEMA}:" + (f"{layer}:" if layer else "") + (f"{scope}:" if scope else "")
    keys = _try(lambda: backend().keys(prefix), "cache", prefix) or []
    if keys:
        _try(lambda: backend().delete(*keys), "cache", prefix)
    return len(keys)
