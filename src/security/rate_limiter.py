"""
Sliding-window rate limiter keyed by IP address.

Each IP is allowed `max_requests` within a rolling `window_seconds` window.
Thread-safe - uses a single lock around the timestamps dict.

Usage:
    limiter = RateLimiter(max_requests=5, window_seconds=3600)
    allowed, retry_after = limiter.check("192.168.1.1")
    if not allowed:
        raise HTTPException(429, f"Too many requests. Try again in {retry_after}s.")
"""

import threading
import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class RateLimiter:
    max_requests: int = 10        # requests allowed per window
    window_seconds: int = 3600    # rolling window size in seconds

    _store: dict[str, deque] = field(default_factory=dict, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def check(self, ip: str) -> tuple[bool, int]:
        """
        Check whether `ip` is within the rate limit.

        Returns:
            (allowed: bool, retry_after_seconds: int)
            retry_after is 0 when allowed, positive when blocked.
        """
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            if ip not in self._store:
                self._store[ip] = deque()

            timestamps = self._store[ip]

            # Remove requests outside the current window
            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()

            if len(timestamps) < self.max_requests:
                timestamps.append(now)
                return True, 0

            # Blocked: calculate how long until the oldest request expires
            oldest = timestamps[0]
            retry_after = int(self.window_seconds - (now - oldest)) + 1
            return False, retry_after

    def remaining(self, ip: str) -> int:
        """Return how many requests the IP still has in the current window."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            if ip not in self._store:
                return self.max_requests
            timestamps = self._store[ip]
            active = sum(1 for t in timestamps if t >= cutoff)
            return max(0, self.max_requests - active)

    def reset(self, ip: str) -> None:
        """Clear rate limit for a specific IP (useful in tests)."""
        with self._lock:
            self._store.pop(ip, None)
