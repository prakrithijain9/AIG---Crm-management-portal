"""Per-key sliding-window rate limit, kept in process memory.

With more than one uvicorn worker each worker counts separately, so the effective limit is
the setting times the number of workers. Good enough to stop a runaway client from burning
the free-tier quota; it is not a security boundary.
"""

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable


class RateLimiter:
    def __init__(self, window_seconds: float = 60.0, clock: Callable[[], float] = time.monotonic):
        self.window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int) -> float | None:
        """Record a request. Returns None if allowed, else seconds until the next slot."""
        now = self._clock()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= limit:
                return max(self.window - (now - hits[0]), 0.0)
            hits.append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


chat_limiter = RateLimiter()
