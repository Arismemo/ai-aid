import time
from collections import defaultdict, deque
from threading import Lock


def _now_ms() -> int:
    return int(time.time() * 1000)


class SlidingWindow:
    def __init__(self, limit: int, window_ms: int):
        self.limit = limit
        self.window_ms = window_ms
        self._buckets: dict[str, deque[int]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = _now_ms()
        cutoff = now - self.window_ms
        with self._lock:
            bucket = self._buckets[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return False
            bucket.append(now)
            return True
