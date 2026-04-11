"""
Tests for RateLimiter - no network calls, pure logic.
"""

import time
import pytest
from src.security.rate_limiter import RateLimiter


class TestRateLimiter:
    def test_first_request_is_allowed(self):
        rl = RateLimiter(max_requests=5, window_seconds=60)
        allowed, retry_after = rl.check("1.2.3.4")
        assert allowed is True
        assert retry_after == 0

    def test_requests_within_limit_are_allowed(self):
        rl = RateLimiter(max_requests=5, window_seconds=60)
        for _ in range(5):
            allowed, _ = rl.check("1.2.3.4")
            assert allowed is True

    def test_exceeding_limit_is_blocked(self):
        rl = RateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            rl.check("1.2.3.4")
        allowed, retry_after = rl.check("1.2.3.4")
        assert allowed is False
        assert retry_after > 0

    def test_different_ips_are_independent(self):
        rl = RateLimiter(max_requests=1, window_seconds=60)
        allowed_a, _ = rl.check("1.1.1.1")
        allowed_b, _ = rl.check("2.2.2.2")
        assert allowed_a is True
        assert allowed_b is True

    def test_second_request_from_same_ip_blocked_at_limit_1(self):
        rl = RateLimiter(max_requests=1, window_seconds=60)
        rl.check("1.2.3.4")
        allowed, retry_after = rl.check("1.2.3.4")
        assert allowed is False
        assert 0 < retry_after <= 60

    def test_retry_after_is_positive_and_bounded(self):
        rl = RateLimiter(max_requests=1, window_seconds=3600)
        rl.check("1.2.3.4")
        _, retry_after = rl.check("1.2.3.4")
        assert 0 < retry_after <= 3601

    def test_remaining_decrements_with_requests(self):
        rl = RateLimiter(max_requests=5, window_seconds=60)
        assert rl.remaining("1.2.3.4") == 5
        rl.check("1.2.3.4")
        assert rl.remaining("1.2.3.4") == 4
        rl.check("1.2.3.4")
        assert rl.remaining("1.2.3.4") == 3

    def test_remaining_never_goes_below_zero(self):
        rl = RateLimiter(max_requests=2, window_seconds=60)
        for _ in range(5):
            rl.check("1.2.3.4")
        assert rl.remaining("1.2.3.4") == 0

    def test_reset_clears_ip_history(self):
        rl = RateLimiter(max_requests=1, window_seconds=60)
        rl.check("1.2.3.4")
        rl.reset("1.2.3.4")
        allowed, _ = rl.check("1.2.3.4")
        assert allowed is True

    def test_window_expiry_allows_new_requests(self):
        rl = RateLimiter(max_requests=1, window_seconds=1)
        rl.check("1.2.3.4")
        allowed_before, _ = rl.check("1.2.3.4")
        assert allowed_before is False

        time.sleep(1.1)  # wait for window to expire

        allowed_after, _ = rl.check("1.2.3.4")
        assert allowed_after is True

    def test_thread_safety_concurrent_requests(self):
        import threading
        rl = RateLimiter(max_requests=100, window_seconds=60)
        results = []
        lock = threading.Lock()

        def make_request():
            allowed, _ = rl.check("shared-ip")
            with lock:
                results.append(allowed)

        threads = [threading.Thread(target=make_request) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        allowed_count = sum(1 for r in results if r)
        assert allowed_count == 50  # all should pass since limit is 100
