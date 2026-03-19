from collections import defaultdict, deque
from threading import Lock
from time import time


class InMemoryRateLimiter:
    """Best-effort in-process limiter keyed by arbitrary string values."""

    def __init__(self) -> None:
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str, limit: int, period_seconds: int) -> bool:
        now = time()
        cutoff = now - period_seconds

        with self._lock:
            bucket = self._requests[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()

            if len(bucket) >= limit:
                return False

            bucket.append(now)
            return True


auth_rate_limiter = InMemoryRateLimiter()
