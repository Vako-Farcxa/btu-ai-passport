"""A tiny in-process cache with a time limit, for read-mostly admin data.

The API runs as one process, so a dict behind a lock is enough. Entries expire after `ttl`
seconds, and every admin write (and every test) clears them, so the dashboard never shows a
number older than a few seconds and never hides a change the admin just made.
"""

import threading
import time
from collections.abc import Callable

_all: list["TtlCache[object]"] = []


class TtlCache[T]:
    def __init__(self, ttl: float) -> None:
        self.ttl = ttl
        self._lock = threading.Lock()
        self._items: dict[str, tuple[float, T]] = {}
        _all.append(self)  # type: ignore[arg-type]

    def get(self, key: str) -> T | None:
        with self._lock:
            found = self._items.get(key)
            if found is None or found[0] <= time.monotonic():
                self._items.pop(key, None)
                return None
            return found[1]

    def put(self, key: str, value: T) -> None:
        with self._lock:
            self._items[key] = (time.monotonic() + self.ttl, value)

    def get_or_load(self, key: str, load: Callable[[], T]) -> T:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = load()
        self.put(key, value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


def clear_all_caches() -> None:
    for cache in _all:
        cache.clear()
