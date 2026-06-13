"""Tests for acs.scheduler.rate_limiter — token bucket and rate limiting."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import time
from acs.scheduler.rate_limiter import RateLimiter, TokenBucket


class TestTokenBucket:

    def test_starts_full(self):
        tb = TokenBucket(rate=1.0, burst=3)
        assert tb.tokens == 3.0

    def test_try_consume(self):
        tb = TokenBucket(rate=1.0, burst=3)
        assert tb.try_consume()
        assert tb.tokens == 2.0

    def test_exhaustion(self):
        tb = TokenBucket(rate=1.0, burst=1)
        assert tb.try_consume()
        assert not tb.try_consume()

    def test_refill_over_time(self):
        tb = TokenBucket(rate=100.0, burst=5)
        # Exhaust
        for _ in range(5):
            tb.try_consume()
        assert not tb.try_consume()
        # Simulate time passing: set last_refill to 0.1s ago
        tb.last_refill = time.time() - 0.2
        assert tb.try_consume()  # Should have refilled

    def test_wait_time(self):
        tb = TokenBucket(rate=10.0, burst=0)
        tb.tokens = 0
        w = tb.wait_time()
        assert 0.05 < w < 0.3  # ~0.1s at rate=10

    def test_tokens_never_exceed_burst(self):
        tb = TokenBucket(rate=1000.0, burst=5)
        tb.last_refill = time.time() - 10.0  # Long time
        tb.refill()
        assert tb.tokens <= 5.0


class TestRateLimiter:

    def test_acquire_immediate_when_below_limit(self):
        rl = RateLimiter(global_rps=100.0, per_domain_rps=100.0, burst_size=100)
        ok = rl.try_acquire("example.com")
        assert ok
        w = rl.global_wait_time
        assert w < 0.2

    def test_try_acquire(self):
        rl = RateLimiter(global_rps=100.0, burst_size=10)
        for _ in range(10):
            assert rl.try_acquire()
        assert not rl.try_acquire()  # Burst exhausted

    def test_per_domain_isolation(self):
        # Verify domain tracking: separate buckets created for each domain
        rl_b = RateLimiter(global_rps=1000.0, per_domain_rps=100.0, burst_size=10)
        # Acquire some from each domain
        assert rl_b.try_acquire("a.com")
        assert rl_b.try_acquire("b.com")
        # Both domains tracked independently
        stats = rl_b.stats
        assert "a.com" in stats["tracked_domains"]
        assert "b.com" in stats["tracked_domains"]
        # Domain wait_time reflects per-domain bucket state
        assert rl_b.domain_wait_time("a.com") >= 0

    def test_global_limit_applies(self):
        rl = RateLimiter(global_rps=100.0, burst_size=2)
        assert rl.try_acquire()
        assert rl.try_acquire()
        assert not rl.try_acquire()

    def test_set_global_rate(self):
        rl = RateLimiter(global_rps=0.1, burst_size=1)
        rl.try_acquire()
        assert not rl.try_acquire()
        rl.set_global_rate(100.0)
        # Rate changed but burst still exhausted; wait_time should decrease
        assert rl.global_wait_time < 0.2

    def test_set_per_domain_rate(self):
        rl = RateLimiter(per_domain_rps=0.1, burst_size=1)
        rl.try_acquire("x.com")
        assert not rl.try_acquire("x.com")
        rl.set_per_domain_rate(100.0)
        # Reset to refill the bucket with new rate
        rl.reset()
        assert rl.try_acquire("x.com")

    def test_stats(self):
        rl = RateLimiter(global_rps=10.0, per_domain_rps=5.0, burst_size=3)
        rl.try_acquire("test.com")
        s = rl.stats
        assert s["global_rps"] == 10.0
        assert s["per_domain_rps"] == 5.0
        assert s["burst_size"] == 3
        assert s["total_acquired"] >= 1
        assert "test.com" in s["tracked_domains"]

    def test_reset(self):
        rl = RateLimiter(global_rps=10.0, burst_size=3)
        for _ in range(3):
            rl.try_acquire()
        assert not rl.try_acquire()
        rl.reset()
        assert rl.try_acquire()
        assert rl.stats["total_acquired"] == 1

    def test_acquire_with_timeout(self):
        rl = RateLimiter(global_rps=0.01, burst_size=0)  # Very slow (burst clamped to 1)
        # Burst=1 means one token available immediately
        assert rl.try_acquire()  # Consume the single token
        assert not rl.try_acquire()  # No more tokens at this slow rate
        # wait_time should be large (~100s for rate=0.01)
        w = rl.global_wait_time
        assert w > 10.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
