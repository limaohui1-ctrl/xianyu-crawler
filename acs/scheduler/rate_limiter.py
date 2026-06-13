"""
Rate limiter — global and per-domain request throttling.

Implements token-bucket algorithm for smooth rate limiting.
Supports:
  - Global rate limit (requests/second across all domains)
  - Per-domain rate limit (requests/second for each domain)
  - Burst tolerance (allow short bursts up to burst_size)
  - Thread-safe

Usage:
    from acs.scheduler.rate_limiter import RateLimiter

    limiter = RateLimiter(global_rps=2.0, per_domain_rps=1.0)
    limiter.acquire("example.com")  # blocks until a token is available
"""

from dataclasses import dataclass, field
from typing import Dict, Optional
import threading
import time


@dataclass
class TokenBucket:
    """A single token bucket for rate limiting."""

    rate: float = 1.0            # tokens per second
    burst: int = 3               # max burst (bucket capacity)
    tokens: float = 0.0          # current token count
    last_refill: float = field(default_factory=time.time)

    def __post_init__(self):
        self.tokens = float(self.burst)  # start full

    def refill(self):
        """Add tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(float(self.burst), self.tokens + elapsed * self.rate)
        self.last_refill = now

    def try_consume(self) -> bool:
        """Consume one token if available. Returns True if consumed."""
        self.refill()
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False

    def wait_time(self) -> float:
        """Estimated seconds until next token."""
        self.refill()
        if self.tokens >= 1.0:
            return 0.0
        return (1.0 - self.tokens) / max(self.rate, 0.001)


class RateLimiter:
    """Thread-safe rate limiter with global + per-domain token buckets.

    Args:
        global_rps: Maximum global requests per second
        per_domain_rps: Maximum requests per second per domain
        burst_size: Max burst size (tokens accumulated during idle periods)
    """

    def __init__(
        self,
        global_rps: float = 2.0,
        per_domain_rps: float = 1.0,
        burst_size: int = 3,
    ):
        self._lock = threading.Lock()
        self._global = TokenBucket(
            rate=max(0.01, global_rps),
            burst=max(1, burst_size),
        )
        self._domain_rate = max(0.01, per_domain_rps)
        self._burst_size = max(1, burst_size)
        self._domain_buckets: Dict[str, TokenBucket] = {}
        self._total_acquired: int = 0
        self._total_wait_seconds: float = 0.0

    # ── Public API ───────────────────────────────────────────────

    def acquire(self, domain: str = "", timeout: float = 0.0) -> float:
        """Acquire permission to make a request. May block.

        Args:
            domain: Domain being requested (for per-domain limiting)
            timeout: Max seconds to wait (0 = wait indefinitely)

        Returns:
            Seconds actually waited
        """
        waited = 0.0
        deadline = time.time() + timeout if timeout > 0 else float("inf")

        while True:
            with self._lock:
                global_ok = self._global.try_consume()
                domain_ok = self._try_domain(domain) if domain else True

                if global_ok and domain_ok:
                    self._total_acquired += 1
                    self._total_wait_seconds += waited
                    return waited

                # Calculate wait time
                wait = 0.0
                if not global_ok:
                    wait = max(wait, self._global.wait_time())
                if not domain_ok and domain:
                    bucket = self._get_or_create_bucket(domain)
                    wait = max(wait, bucket.wait_time())

                wait = max(0.01, min(wait, 5.0))  # clamp

            # Sleep outside lock
            if timeout > 0 and time.time() + wait > deadline:
                break
            time.sleep(wait)
            waited += wait

        return waited

    def try_acquire(self, domain: str = "") -> bool:
        """Non-blocking: try to acquire, return immediately."""
        with self._lock:
            if self._global.try_consume():
                if not domain or self._try_domain(domain):
                    self._total_acquired += 1
                    return True
        return False

    def set_global_rate(self, rps: float):
        """Adjust global rate limit at runtime."""
        with self._lock:
            self._global.rate = max(0.01, rps)

    def set_per_domain_rate(self, rps: float):
        """Adjust per-domain rate limit at runtime."""
        with self._lock:
            self._domain_rate = max(0.01, rps)
            # Update all existing domain buckets
            for bucket in self._domain_buckets.values():
                bucket.rate = self._domain_rate

    # ── Queries ──────────────────────────────────────────────────

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "global_rps": self._global.rate,
                "per_domain_rps": self._domain_rate,
                "burst_size": self._burst_size,
                "total_acquired": self._total_acquired,
                "total_wait_seconds": round(self._total_wait_seconds, 3),
                "tracked_domains": list(self._domain_buckets.keys()),
            }

    @property
    def global_wait_time(self) -> float:
        """Estimated wait for next global token."""
        with self._lock:
            return self._global.wait_time()

    def domain_wait_time(self, domain: str) -> float:
        """Estimated wait for next per-domain token."""
        with self._lock:
            return self._get_or_create_bucket(domain).wait_time()

    def reset(self):
        """Reset all state."""
        with self._lock:
            self._global = TokenBucket(
                rate=self._global.rate,
                burst=self._burst_size,
            )
            self._domain_buckets.clear()
            self._total_acquired = 0
            self._total_wait_seconds = 0.0

    # ── Internals ────────────────────────────────────────────────

    def _get_or_create_bucket(self, domain: str) -> TokenBucket:
        """Get or create a per-domain bucket. Caller must hold lock."""
        if domain not in self._domain_buckets:
            self._domain_buckets[domain] = TokenBucket(
                rate=self._domain_rate,
                burst=self._burst_size,
            )
        return self._domain_buckets[domain]

    def _try_domain(self, domain: str) -> bool:
        """Try to consume from domain bucket. Caller must hold lock."""
        return self._get_or_create_bucket(domain).try_consume()
