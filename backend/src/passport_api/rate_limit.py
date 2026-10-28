import threading
import time


class RateLimiter:
    """Sliding-window in-memory rate limiter per IP address."""

    def __init__(self, max_requests: int = 30, window_seconds: float = 60.0) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        """Returns True if request is allowed, False if rate limited."""
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            timestamps = self._requests.get(key, [])
            valid_timestamps = [t for t in timestamps if t > cutoff]
            if len(valid_timestamps) >= self.max_requests:
                self._requests[key] = valid_timestamps
                return False
            valid_timestamps.append(now)
            self._requests[key] = valid_timestamps
            return True

    def reset(self) -> None:
        """Clear all stored rate limit records (useful for testing)."""
        with self._lock:
            self._requests.clear()


# Default verify rate limiter: 30 requests per 60 seconds per IP
verify_limiter = RateLimiter(max_requests=30, window_seconds=60.0)
