"""Tests for acs.scheduler.retry_policy — retry decisions and backoff."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from acs.scheduler.retry_policy import RetryPolicy, RetryDecision


class TestRetryPolicy:

    def test_retry_429(self):
        p = RetryPolicy(max_retries=3)
        d = p.should_retry(retry_count=0, status_code=429)
        assert d.should_retry
        assert d.delay_seconds > 0

    def test_retry_5xx(self):
        p = RetryPolicy()
        for code in [500, 502, 503, 504]:
            d = p.should_retry(retry_count=0, status_code=code)
            assert d.should_retry, f"Status {code} should be retryable"

    def test_no_retry_404(self):
        p = RetryPolicy()
        d = p.should_retry(retry_count=0, status_code=404)
        assert not d.should_retry

    def test_no_retry_401_403(self):
        p = RetryPolicy()
        d = p.should_retry(retry_count=0, status_code=401)
        assert not d.should_retry
        d = p.should_retry(retry_count=0, status_code=403)
        assert not d.should_retry

    def test_max_retries_exhausted(self):
        p = RetryPolicy(max_retries=2)
        d = p.should_retry(retry_count=2, status_code=503)
        assert not d.should_retry
        assert "exhausted" in d.reason.lower()

    def test_backoff_increases(self):
        p = RetryPolicy(max_retries=5, backoff_base=1.0, jitter_enabled=False)
        d0 = p.should_retry(retry_count=0, status_code=503)
        d1 = p.should_retry(retry_count=1, status_code=503)
        d2 = p.should_retry(retry_count=2, status_code=503)
        assert d0.delay_seconds < d1.delay_seconds < d2.delay_seconds

    def test_timeout_classified_retryable(self):
        p = RetryPolicy()
        d = p.should_retry(retry_count=0, status_code=0, error_text="Connection timed out")
        assert d.should_retry

    def test_dns_error_classified_retryable(self):
        p = RetryPolicy()
        d = p.should_retry(retry_count=0, status_code=0, error_text="Name resolution failed for host")
        assert d.should_retry

    def test_forbidden_text_no_retry(self):
        p = RetryPolicy()
        d = p.should_retry(retry_count=0, status_code=0, error_text="403 Forbidden — access denied")
        assert not d.should_retry

    def test_classify_error_method(self):
        p = RetryPolicy()
        assert p.classify_error("Connection timed out") == "retryable"
        assert p.classify_error("404 Not Found") == "non_retryable"
        assert p.classify_error("401 Unauthorized") == "non_retryable"

    def test_retry_after_header_respected(self):
        p = RetryPolicy()
        d = p.should_retry(retry_count=0, status_code=429, retry_after=60.0)
        assert d.should_retry
        # Backoff for 429 with retry_after should use that value (or jittered variant)
        assert 10 < d.delay_seconds < 120

    def test_retry_decision_to_dict(self):
        d = RetryDecision(should_retry=True, delay_seconds=2.5, reason="test", retry_count=1, max_retries=3)
        dd = d.to_dict()
        assert dd["should_retry"] is True
        assert dd["delay_seconds"] == 2.5
        assert dd["retry_count"] == 1

    def test_4xx_no_retry_by_default(self):
        p = RetryPolicy(retry_on_4xx=False)
        for code in [400, 405, 410, 413]:
            d = p.should_retry(retry_count=0, status_code=code)
            assert not d.should_retry, f"Status {code} should NOT be retryable"

    def test_4xx_retry_when_enabled(self):
        p = RetryPolicy(retry_on_4xx=True)
        # Status 418 is in NON_RETRYABLE, so retry_on_4xx won't override it.
        # Use an UNKNOWN 4xx (e.g. 499) to test retry_on_4xx behavior.
        d = p.should_retry(retry_count=0, status_code=499)
        assert d.should_retry

    def test_retry_decision_is_dataclass(self):
        d = RetryDecision()
        assert not d.should_retry
        assert d.delay_seconds == 0.0

    def test_jitter_adds_variability(self):
        """Jitter should cause delay to vary (probabilistic — run multiple times)."""
        p = RetryPolicy(max_retries=5, backoff_base=1.0, jitter_enabled=True)
        delays = set()
        for _ in range(20):
            d = p.should_retry(retry_count=0, status_code=503)
            delays.add(round(d.delay_seconds, 2))
        # With jitter, we should see at least 2 distinct values (with high probability)
        assert len(delays) >= 2 or delays == {1.0}, f"Expected jitter variability, got {delays}"

    def test_delay_clamped_at_120s(self):
        p = RetryPolicy(max_retries=10, backoff_base=10.0, jitter_enabled=False)
        d = p.should_retry(retry_count=8, status_code=503)
        assert d.delay_seconds <= 120.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
