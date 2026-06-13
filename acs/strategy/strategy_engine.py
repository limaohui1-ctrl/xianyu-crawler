"""
Strategy engine — the central decision layer for ACS crawl behavior.

Ties together:
  - CrawlMode selection and transitions
  - RetryPolicy for per-request retry decisions
  - RateLimiter for global + per-domain throttling
  - CostController for resource tracking and limits
  - Shadow comparison data for quality assessment

The engine provides recommendations; it does NOT directly modify
the crawl loop.  The caller (UniversalCollector or a future ACS
collector) reads engine state and adjusts behavior accordingly.

Usage:
    from acs.strategy.strategy_engine import StrategyEngine
    from acs.strategy.crawl_modes import CrawlMode

    engine = StrategyEngine()
    engine.set_mode(CrawlMode.FULL)

    # After each request:
    engine.record_request("https://example.com/page", success=True)
    engine.record_shadow_parse()

    # Query state:
    if engine.should_degrade:
        engine.set_mode(CrawlMode.DEGRADED)
    if engine.should_stop:
        break

    # Per-request retry:
    decision = engine.should_retry(retry_count=2, status_code=429)
    if decision.should_retry:
        time.sleep(decision.delay_seconds)
        # re-request
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import threading
import time

from acs.strategy.crawl_modes import (
    CrawlMode, ModeConfig, get_mode_config, MODE_DEFAULTS,
)
from acs.strategy.cost_controller import CostController, CostSummary
from acs.scheduler.retry_policy import RetryPolicy, RetryDecision
from acs.scheduler.rate_limiter import RateLimiter


@dataclass
class StrategyState:
    """Current strategy engine state snapshot."""

    active_mode: str = "full"
    degraded: bool = False
    stopped: bool = False
    cost_summary: Optional[Dict] = None
    mode_config: Optional[Dict] = None
    rate_limiter_stats: Optional[Dict] = None
    transition_history: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "active_mode": self.active_mode,
            "degraded": self.degraded,
            "stopped": self.stopped,
            "cost_summary": self.cost_summary,
            "mode_config": self.mode_config,
            "rate_limiter_stats": self.rate_limiter_stats,
            "transition_history": self.transition_history,
        }


class StrategyEngine:
    """Central strategy decision layer.

    Provides:
      - Mode management (fast/full/conservative/degraded/...)
      - Retry decisions (via RetryPolicy, synced with current mode)
      - Rate limiting (via RateLimiter, synced with current mode)
      - Cost tracking (via CostController)
      - Automatic degrade/stop detection

    All methods are thread-safe.
    """

    def __init__(
        self,
        initial_mode: CrawlMode = CrawlMode.FULL,
        max_requests: int = 1000,
        max_failure_rate: float = 0.3,
        max_total_failures: int = 100,
    ):
        self._lock = threading.RLock()
        self._mode: CrawlMode = initial_mode
        self._mode_config: ModeConfig = get_mode_config(initial_mode)
        self._transition_history: List[Dict[str, str]] = []

        # Sub-components — may be replaced on mode change
        self.cost_controller = CostController(
            max_requests=max_requests,
            max_failure_rate=max_failure_rate,
            max_total_failures=max_total_failures,
        )
        self.retry_policy = RetryPolicy(
            max_retries=self._mode_config.max_retries,
            backoff_base=self._mode_config.retry_backoff_base,
            jitter_enabled=self._mode_config.jitter_enabled,
            retry_on_4xx=self._mode_config.retry_on_4xx,
        )
        self.rate_limiter = RateLimiter(
            global_rps=self._mode_config.requests_per_second,
            per_domain_rps=self._mode_config.requests_per_domain_per_second,
            burst_size=self._mode_config.burst_size,
        )

        # Shadow analysis data (accumulated)
        self._shadow_superior_count: int = 0
        self._shadow_inferior_count: int = 0
        self._shadow_equal_count: int = 0
        self._shadow_errors: List[Dict[str, str]] = []

    # ── Mode management ──────────────────────────────────────────

    @property
    def active_mode(self) -> CrawlMode:
        with self._lock:
            return self._mode

    @property
    def mode_config(self) -> ModeConfig:
        with self._lock:
            return self._mode_config

    def set_mode(self, mode: CrawlMode, reason: str = ""):
        """Switch to a new crawl mode and update all sub-components."""
        with self._lock:
            old = self._mode.value
            self._mode = mode
            self._mode_config = get_mode_config(mode)

            entry = {
                "from": old,
                "to": mode.value,
                "reason": reason,
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            self._transition_history.append(entry)

            # Keep last 50 transitions
            if len(self._transition_history) > 50:
                self._transition_history = self._transition_history[-50:]

            # Update sub-components
            cfg = self._mode_config
            self.retry_policy.max_retries = cfg.max_retries
            self.retry_policy.backoff_base = cfg.retry_backoff_base
            self.retry_policy.jitter_enabled = cfg.jitter_enabled
            self.retry_policy.retry_on_4xx = cfg.retry_on_4xx

            self.rate_limiter.set_global_rate(cfg.requests_per_second)
            self.rate_limiter.set_per_domain_rate(cfg.requests_per_domain_per_second)

    # ── Decision triggers (automatic) ────────────────────────────

    @property
    def should_degrade(self) -> bool:
        """Should we switch to degraded mode?"""
        return self.cost_controller.should_degrade and self._mode != CrawlMode.DEGRADED

    @property
    def should_stop(self) -> bool:
        """Should we stop the crawl entirely?"""
        return self.cost_controller.should_stop

    def check_and_adapt(self) -> Optional[str]:
        """Check conditions and automatically switch mode if needed.

        Returns the action taken (or None if no action needed).
        """
        with self._lock:
            # Stop takes highest priority
            if self.cost_controller.should_stop and self._mode != CrawlMode.DEGRADED:
                self.set_mode(CrawlMode.DEGRADED, "cost_controller: should_stop")
                self.cost_controller.mark_stopped("Strategy engine auto-stop")
                return "stopped"

            # Degrade on threshold breach
            if self.should_degrade:
                self.set_mode(CrawlMode.DEGRADED, "cost_controller: failure_rate exceeded")
                self.cost_controller.mark_degraded()
                return "degraded"

            return None

    # ── Per-request helpers ──────────────────────────────────────

    def should_retry(
        self,
        retry_count: int,
        status_code: int = 0,
        error_text: str = "",
        retry_after: Optional[float] = None,
    ) -> RetryDecision:
        """Check if a failed request should be retried."""
        decision = self.retry_policy.should_retry(
            retry_count=retry_count,
            status_code=status_code,
            error_text=error_text,
            retry_after=retry_after,
        )
        return decision

    def acquire_rate_limit(self, domain: str, timeout: float = 0.0) -> float:
        """Wait for rate-limit permission. Returns seconds waited."""
        return self.rate_limiter.acquire(domain, timeout=timeout)

    # ── Recording ────────────────────────────────────────────────

    def record_request(self, url: str = "", domain: str = "", success: bool = True):
        """Record a fetch attempt."""
        self.cost_controller.record_request()
        if success:
            self.cost_controller.record_success()
        else:
            self.cost_controller.record_failure(url)

    def record_retry(self):
        """Record a retry attempt."""
        self.cost_controller.record_retry()

    def record_failure(self, url: str, error: str = ""):
        """Record a failed fetch with error details."""
        self.cost_controller.record_failure(url, error)

    def record_shadow_parse(self):
        """Record that ACS shadow parser ran."""
        self.cost_controller.record_shadow_parse()

    def record_shadow_comparison(
        self,
        url: str,
        acs_quality: int,
        legacy_quality: int,
        acs_parser: str = "",
    ):
        """Record the outcome of an ACS vs legacy comparison."""
        with self._lock:
            if acs_quality > legacy_quality + 10:
                self._shadow_superior_count += 1
            elif legacy_quality > acs_quality + 10:
                self._shadow_inferior_count += 1
                if len(self._shadow_errors) < 100:
                    self._shadow_errors.append({
                        "url": url,
                        "acs_quality": str(acs_quality),
                        "legacy_quality": str(legacy_quality),
                        "acs_parser": acs_parser,
                    })
            else:
                self._shadow_equal_count += 1

    # ── Queries ──────────────────────────────────────────────────

    def get_state(self) -> StrategyState:
        """Get a snapshot of current engine state."""
        with self._lock:
            return StrategyState(
                active_mode=self._mode.value,
                degraded=self._mode == CrawlMode.DEGRADED,
                stopped=self.cost_controller.should_stop,
                cost_summary=self.cost_controller.get_summary().to_dict(),
                mode_config=self._mode_config.to_dict(),
                rate_limiter_stats=self.rate_limiter.stats,
                transition_history=list(self._transition_history),
            )

    def get_shadow_stats(self) -> dict:
        """Get ACS shadow comparison statistics."""
        with self._lock:
            total = (self._shadow_superior_count +
                     self._shadow_inferior_count +
                     self._shadow_equal_count)
            return {
                "superior": self._shadow_superior_count,
                "inferior": self._shadow_inferior_count,
                "equal": self._shadow_equal_count,
                "total_compared": total,
                "superior_pct": round(
                    self._shadow_superior_count / max(total, 1) * 100, 1
                ),
                "inferior_pct": round(
                    self._shadow_inferior_count / max(total, 1) * 100, 1
                ),
                "recommendation": self._shadow_recommendation(),
            }

    def _shadow_recommendation(self) -> str:
        """Generate a recommendation based on shadow comparison data."""
        total = (self._shadow_superior_count +
                 self._shadow_inferior_count +
                 self._shadow_equal_count)
        if total < 50:
            return "insufficient_data — keep shadow mode, gather more samples"
        if self._shadow_superior_count > self._shadow_inferior_count * 1.5:
            return "acs_performs_better — candidate for on mode after further validation"
        if self._shadow_inferior_count > self._shadow_superior_count * 1.5:
            return "acs_performs_worse — do NOT switch to on mode; investigate inferior cases"
        return "comparable — keep shadow mode for now"

    def reset(self):
        """Reset all state (for testing)."""
        with self._lock:
            self._mode = CrawlMode.FULL
            self._mode_config = get_mode_config(CrawlMode.FULL)
            self._transition_history = []
            self._shadow_superior_count = 0
            self._shadow_inferior_count = 0
            self._shadow_equal_count = 0
            self._shadow_errors = []
            self.cost_controller.reset()
            self.rate_limiter.reset()

    # ── Convenience: create with standard presets ────────────────

    @classmethod
    def create_default(cls) -> "StrategyEngine":
        return cls(initial_mode=CrawlMode.FULL)

    @classmethod
    def create_conservative(cls) -> "StrategyEngine":
        return cls(
            initial_mode=CrawlMode.CONSERVATIVE,
            max_requests=200,
            max_failure_rate=0.2,
            max_total_failures=20,
        )
