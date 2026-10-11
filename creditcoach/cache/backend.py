"""Where cached values are kept: Redis when ``REDIS_URL`` is set, otherwise this process's memory.

Both backends store strings under string keys with a time to live, which is all the cache layers need
(``creditcoach.cache``). Redis is the real store: it is shared by every process and survives a restart of the app.
The memory backend lets a fresh clone run with no Redis at all, and is what the tests use besides a fake Redis.

Example:
    >>> from creditcoach.cache import backend
    >>> store = backend.MemoryBackend(max_items=100)
    >>> store.set("k", "v", ttl=60); store.get("k")
    'v'
"""

import threading
import time
from collections import OrderedDict


class MemoryBackend:
    """An in-process store with a time to live per key and a size cap (least recently used goes first)."""

    name = "memory"

    def __init__(self, max_items: int = 5000):
        self.max_items = max_items
        self._items: OrderedDict[str, tuple[float, str]] = OrderedDict()  # key -> (expires at, value)
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            if item[0] <= time.time():
                del self._items[key]
                return None
            self._items.move_to_end(key)
            return item[1]

    def set(self, key: str, value: str, ttl: int) -> None:
        with self._lock:
            self._items[key] = (time.time() + ttl, value)
            self._items.move_to_end(key)
            while len(self._items) > self.max_items:
                self._items.popitem(last=False)

    def delete(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._items.pop(key, None)

    def incr(self, key: str) -> None:
        with self._lock:
            _, value = self._items.get(key, (0, "0"))
            self._items[key] = (float("inf"), str(int(value) + 1))

    def keys(self, prefix: str) -> list[str]:
        with self._lock:
            now = time.time()
            return [k for k, (expires, _) in self._items.items() if k.startswith(prefix) and expires > now]


class RedisBackend:
    """Redis, through ``redis-py``. Short timeouts, so a slow or missing Redis costs an answer a fraction of a
    second rather than stalling it; the cache layers treat any error as a miss."""

    name = "redis"

    def __init__(self, url: str, client=None, timeout: float = 0.5):
        import redis

        self.client = client or redis.Redis.from_url(url, decode_responses=True, socket_timeout=timeout,
                                                     socket_connect_timeout=timeout)

    def get(self, key: str) -> str | None:
        return self.client.get(key)

    def set(self, key: str, value: str, ttl: int) -> None:
        self.client.set(key, value, ex=ttl)

    def delete(self, *keys: str) -> None:
        if keys:
            self.client.delete(*keys)

    def incr(self, key: str) -> None:
        self.client.incr(key)

    def keys(self, prefix: str) -> list[str]:
        return list(self.client.scan_iter(match=prefix + "*", count=500))
