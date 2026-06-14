"""
AI Parse Policy — decides WHEN to invoke the AI parser.

Enforces strict constraints:
  - AI parser is ALWAYS a fallback, never the first parser
  - Only called when conventional parsers fail or produce low-quality results
  - Must respect cost limits (delegates to CostController)
  - Single-URL AI call limits
  - Must have user opt-in for persistent AI usage

Usage:
    from acs.strategy.ai_parse_policy import AIParsePolicy, AIParseDecision

    policy = AIParsePolicy(cost_controller=cc)
    decision = policy.should_invoke_ai_parser(
        parse_result=result,
        attempts=[...],
        consecutive_failures=3,
    )
    if decision.should_invoke:
        ai_parser.parse(...)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import threading
import time

from acs.strategy.cost_controller import CostController


@dataclass
class AIParseDecision:
    """Result of AI parse policy evaluation."""

    should_invoke: bool = False
    reason: str = ""
    max_cost_exceeded: bool = False
    ai_calls_remaining: int = 0
    single_url_calls_used: int = 0
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "should_invoke": self.should_invoke,
            "reason": self.reason,
            "max_cost_exceeded": self.max_cost_exceeded,
            "ai_calls_remaining": self.ai_calls_remaining,
            "single_url_calls_used": self.single_url_calls_used,
            "details": self.details,
        }


class AIParsePolicy:
    """Controls when the AI parser can be invoked.

    Enforces:
      - AI parser is fallback only (conventional parsers tried first)
      - Max AI calls per run
      - Max AI calls per URL
      - Must be below cost threshold (via CostController)
      - User must have opted in (ai_fallback_enabled flag)

    Args:
        cost_controller: Phase 3 CostController instance
        max_ai_calls_per_run: Max total AI calls in this run (0 = unlimited)
        max_ai_calls_per_url: Max AI calls per single URL
        ai_fallback_enabled: Master switch for AI parser (default: True for shadow)
    """

    def __init__(
        self,
        cost_controller: Optional[CostController] = None,
        max_ai_calls_per_run: int = 50,
        max_ai_calls_per_url: int = 2,
        ai_fallback_enabled: bool = True,
    ):
        self.cost_controller = cost_controller or CostController()
        self.max_ai_calls_per_run = max_ai_calls_per_run
        self.max_ai_calls_per_url = max_ai_calls_per_url
        self.ai_fallback_enabled = ai_fallback_enabled

        self._lock = threading.Lock()
        self._total_ai_calls: int = 0
        self._per_url_calls: Dict[str, int] = {}
        self._total_ai_tokens: int = 0
        self._estimated_cost: float = 0.0

    # ── Main decision method ─────────────────────────────────────

    def should_invoke_ai_parser(
        self,
        url: str = "",
        parse_result=None,
        parse_attempts: Optional[List] = None,
        consecutive_failures: int = 0,
        missing_critical_fields: Optional[List[str]] = None,
        structure_changed: bool = False,
        user_requested: bool = False,
    ) -> AIParseDecision:
        """Decide whether to invoke the AI parser.

        Args:
            url: Current URL
            parse_result: Current ParseResult (from conventional parsers)
            parse_attempts: List of ParseAttempt from parser_engine
            consecutive_failures: How many consecutive pages failed to parse
            missing_critical_fields: Critical fields that are missing
            structure_changed: Whether DOM structure has changed
            user_requested: Whether user explicitly requested AI parser

        Returns:
            AIParseDecision
        """
        # ── Master switch ──
        if not self.ai_fallback_enabled and not user_requested:
            return AIParseDecision(
                should_invoke=False,
                reason="AI fallback disabled (ai_fallback_enabled=False and not user_requested)",
            )

        # ── Cost check ──
        with self._lock:
            if self.max_ai_calls_per_run > 0 and self._total_ai_calls >= self.max_ai_calls_per_run:
                return AIParseDecision(
                    should_invoke=False,
                    reason=f"AI call limit reached ({self._total_ai_calls}/{self.max_ai_calls_per_run})",
                    max_cost_exceeded=True,
                    ai_calls_remaining=0,
                )

            if self.cost_controller.should_stop or self.cost_controller.should_degrade:
                return AIParseDecision(
                    should_invoke=False,
                    reason="Cost controller: should_stop or should_degrade",
                    max_cost_exceeded=True,
                )

            # ── Per-URL limit ──
            key = self._normalize_url(url)
            url_calls = self._per_url_calls.get(key, 0)
            if self.max_ai_calls_per_url > 0 and url_calls >= self.max_ai_calls_per_url:
                return AIParseDecision(
                    should_invoke=False,
                    reason=f"Per-URL AI call limit reached ({url_calls}/{self.max_ai_calls_per_url})",
                    single_url_calls_used=url_calls,
                )

        # ── User explicitly requested → always allow (if within cost limits) ──
        if user_requested:
            return self._allow("user requested AI parse", url, url_calls)

        # ── All conventional parsers failed ──
        if parse_attempts and all(not a.success for a in parse_attempts):
            return self._allow("all conventional parsers failed", url, url_calls,
                               details={"failed_parsers": [a.parser_name for a in parse_attempts]})

        # ── Critical fields missing ──
        if missing_critical_fields and len(missing_critical_fields) > 0:
            return self._allow(
                f"critical fields missing: {missing_critical_fields}",
                url, url_calls,
                details={"missing_fields": missing_critical_fields},
            )

        # ── Structure changed ──
        if structure_changed:
            return self._allow("DOM structure changed", url, url_calls,
                               details={"structure_changed": True})

        # ── Consecutive failures ──
        if consecutive_failures >= 3:
            return self._allow(f"consecutive failures: {consecutive_failures}", url, url_calls,
                               details={"consecutive_failures": consecutive_failures})

        # ── Low quality ──
        if parse_result and hasattr(parse_result, 'completeness'):
            if parse_result.completeness < 20:
                return self._allow(
                    f"low completeness: {parse_result.completeness}%",
                    url, url_calls,
                    details={"completeness": parse_result.completeness},
                )

        # ── Default: do NOT invoke ──
        return AIParseDecision(
            should_invoke=False,
            reason="No triggering condition met — conventional parser result is sufficient",
            ai_calls_remaining=(self.max_ai_calls_per_run - self._total_ai_calls)
            if self.max_ai_calls_per_run > 0 else -1,
        )

    # ── Recording ────────────────────────────────────────────────

    def record_ai_call(self, url: str, prompt_tokens: int = 0,
                       completion_tokens: int = 0):
        """Record that an AI call was made."""
        with self._lock:
            self._total_ai_calls += 1
            key = self._normalize_url(url)
            self._per_url_calls[key] = self._per_url_calls.get(key, 0) + 1
            self._total_ai_tokens += prompt_tokens + completion_tokens
            # Estimate cost: ~$0.01/1K tokens (adjust per actual model pricing)
            self._estimated_cost += (prompt_tokens + completion_tokens) * 0.00001

    # ── Queries ──────────────────────────────────────────────────

    @property
    def total_ai_calls(self) -> int:
        with self._lock:
            return self._total_ai_calls

    @property
    def total_ai_tokens(self) -> int:
        with self._lock:
            return self._total_ai_tokens

    @property
    def estimated_ai_cost(self) -> float:
        with self._lock:
            return self._estimated_cost

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "ai_fallback_enabled": self.ai_fallback_enabled,
                "total_ai_calls": self._total_ai_calls,
                "max_ai_calls_per_run": self.max_ai_calls_per_run,
                "max_ai_calls_per_url": self.max_ai_calls_per_url,
                "total_ai_tokens": self._total_ai_tokens,
                "estimated_ai_cost": round(self._estimated_cost, 6),
                "unique_urls": len(self._per_url_calls),
            }

    def reset(self):
        """Reset all state (for testing)."""
        with self._lock:
            self._total_ai_calls = 0
            self._per_url_calls = {}
            self._total_ai_tokens = 0
            self._estimated_cost = 0.0

    # ── Internals ────────────────────────────────────────────────

    def _allow(self, reason: str, url: str, url_calls: int = 0,
               details: Optional[dict] = None) -> AIParseDecision:
        remaining = (self.max_ai_calls_per_run - self._total_ai_calls
                     if self.max_ai_calls_per_run > 0 else -1)
        return AIParseDecision(
            should_invoke=True,
            reason=reason,
            ai_calls_remaining=remaining,
            single_url_calls_used=url_calls,
            details=details or {},
        )

    @staticmethod
    def _normalize_url(url: str) -> str:
        from urllib.parse import urlparse
        try:
            p = urlparse(url)
            return f"{p.scheme}://{p.netloc}{p.path}"
        except Exception:
            return url[:200]
