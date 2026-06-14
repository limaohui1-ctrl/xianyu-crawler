"""
Cost controller — tracks and limits crawl resource consumption.

Monitors:
  - Total requests, retries, failures
  - ACS shadow parse count
  - Failure rate
  - Estimated API cost (placeholder, real cost tracking in Phase 4)

Enforces limits:
  - Max requests per run
  - Max retries per URL (delegates to RetryPolicy)
  - Max failure rate threshold → degrade
  - Max total failures → stop

Usage:
    from acs.strategy.cost_controller import CostController

    cc = CostController(max_requests=1000, max_failure_rate=0.3)
    cc.record_request()
    cc.record_failure("https://example.com", "timeout")
    if cc.should_degrade:
        mode = CrawlMode.DEGRADED
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import threading
import time


@dataclass
class CostSummary:
    """Snapshot of current cost/resource state."""

    total_requests: int = 0
    total_retries: int = 0
    total_failures: int = 0
    total_success: int = 0
    shadow_parse_count: int = 0
    estimated_api_cost: float = 0.0        # Placeholder — Phase 4
    max_requests_per_run: int = 1000
    max_retries_per_url: int = 3
    failure_rate: float = 0.0
    should_degrade: bool = False
    should_stop: bool = False
    elapsed_seconds: float = 0.0
    requests_per_minute: float = 0.0

    def to_dict(self) -> dict:
        return {
            "total_requests": self.total_requests,
            "total_retries": self.total_retries,
            "total_failures": self.total_failures,
            "total_success": self.total_success,
            "shadow_parse_count": self.shadow_parse_count,
            "estimated_api_cost": self.estimated_api_cost,
            "max_requests_per_run": self.max_requests_per_run,
            "max_retries_per_url": self.max_retries_per_url,
            "failure_rate": round(self.failure_rate, 4),
            "should_degrade": self.should_degrade,
            "should_stop": self.should_stop,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "requests_per_minute": round(self.requests_per_minute, 1),
        }


class CostController:
    """Tracks and enforces resource limits for a crawl run.

    Thread-safe.  Designed as a singleton per run.

    Args:
        max_requests: Max total requests in this run (0 = unlimited)
        max_retries_per_url: Max retries per individual URL
        max_failure_rate: Failure rate that triggers degrade mode (0.0-1.0)
        max_total_failures: Absolute failure count that triggers stop (0 = unlimited)
    """

    def __init__(
        self,
        max_requests: int = 1000,
        max_retries_per_url: int = 3,
        max_failure_rate: float = 0.3,
        max_total_failures: int = 100,
    ):
        self.max_requests = max_requests
        self.max_retries_per_url = max_retries_per_url
        self.max_failure_rate = max(0.0, min(1.0, max_failure_rate))
        self.max_total_failures = max_total_failures

        self._lock = threading.RLock()
        self._total_requests: int = 0
        self._total_retries: int = 0
        self._total_failures: int = 0
        self._total_success: int = 0
        self._shadow_count: int = 0
        self._start_time: float = time.time()
        self._failure_details: List[Dict[str, str]] = []
        self._degraded_at: Optional[float] = None
        self._stopped_at: Optional[float] = None

    # ── Recording ────────────────────────────────────────────────

    def record_request(self):
        """Record that a request was made (initial attempt)."""
        with self._lock:
            self._total_requests += 1

    def record_retry(self):
        """Record that a retry was attempted."""
        with self._lock:
            self._total_retries += 1

    def record_success(self):
        """Record a successful fetch."""
        with self._lock:
            self._total_success += 1

    def record_failure(self, url: str, error: str = ""):
        """Record a failed fetch."""
        with self._lock:
            self._total_failures += 1
            if len(self._failure_details) < 500:
                self._failure_details.append({
                    "url": url,
                    "error": error[:200],
                    "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                })

    def record_shadow_parse(self):
        """Record that ACS shadow parser ran."""
        with self._lock:
            self._shadow_count += 1

    # ── Thresholds ───────────────────────────────────────────────

    @property
    def failure_rate(self) -> float:
        with self._lock:
            total = self._total_requests
            if total == 0:
                return 0.0
            return self._total_failures / total

    @property
    def should_degrade(self) -> bool:
        """Should we switch to degraded mode?"""
        with self._lock:
            if self._degraded_at is not None:
                return True

            # Hit max requests?
            if self.max_requests > 0 and self._total_requests >= self.max_requests:
                return True

            # Failure rate too high? (inline to avoid lock re-entry)
            rate = self._total_failures / self._total_requests if self._total_requests > 0 else 0.0
            if self._total_requests >= 10 and rate > self.max_failure_rate:
                return True

            return False

    @property
    def should_stop(self) -> bool:
        """Should we stop the crawl entirely?"""
        with self._lock:
            if self._stopped_at is not None:
                return True

            # Absolute failure count exceeded?
            if (self.max_total_failures > 0 and
                    self._total_failures >= self.max_total_failures):
                return True

            # Degraded + continuous failures? (inline to avoid lock re-entry)
            rate = self._total_failures / self._total_requests if self._total_requests > 0 else 0.0
            if (self._degraded_at is not None and
                    self._total_failures > 0 and
                    self._total_requests > 0 and
                    rate > 0.5):
                return True

            return False

    def mark_degraded(self):
        """Manually mark as degraded."""
        with self._lock:
            if self._degraded_at is None:
                self._degraded_at = time.time()

    def mark_stopped(self, reason: str = ""):
        """Manually mark as stopped."""
        with self._lock:
            self._stopped_at = time.time()
            if reason and len(self._failure_details) < 500:
                self._failure_details.append({
                    "url": "_stop_reason",
                    "error": reason[:200],
                    "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                })

    # ── Queries ──────────────────────────────────────────────────

    def get_summary(self) -> CostSummary:
        with self._lock:
            elapsed = time.time() - self._start_time
            rpm = (self._total_requests / max(elapsed, 1)) * 60
            # Inline failure_rate to avoid lock re-entry
            rate = self._total_failures / self._total_requests if self._total_requests > 0 else 0.0
            return CostSummary(
                total_requests=self._total_requests,
                total_retries=self._total_retries,
                total_failures=self._total_failures,
                total_success=self._total_success,
                shadow_parse_count=self._shadow_count,
                max_requests_per_run=self.max_requests,
                max_retries_per_url=self.max_retries_per_url,
                failure_rate=rate,
                should_degrade=self.should_degrade,
                should_stop=self.should_stop,
                elapsed_seconds=elapsed,
                requests_per_minute=rpm,
            )

    def get_summary_text(self) -> str:
        """Human-readable one-line summary."""
        s = self.get_summary()
        status = "NORMAL"
        if s.should_stop:
            status = "STOPPED"
        elif s.should_degrade:
            status = "DEGRADED"
        return (
            f"[{status}] req={s.total_requests} ok={s.total_success} "
            f"fail={s.total_failures} retry={s.total_retries} "
            f"fail_rate={s.failure_rate:.1%} "
            f"shadow={s.shadow_parse_count} "
            f"elapsed={s.elapsed_seconds:.0f}s "
            f"rpm={s.requests_per_minute:.1f}"
        )

    def get_failure_details(self, limit: int = 50) -> List[Dict[str, str]]:
        with self._lock:
            return list(self._failure_details[-limit:])

    def reset(self):
        """Reset all counters (for testing)."""
        with self._lock:
            self._total_requests = 0
            self._total_retries = 0
            self._total_failures = 0
            self._total_success = 0
            self._shadow_count = 0
            self._start_time = time.time()
            self._failure_details = []
            self._degraded_at = None
            self._stopped_at = None
