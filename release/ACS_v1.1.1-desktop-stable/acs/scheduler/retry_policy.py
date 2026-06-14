"""
Retry policy — determines whether a failed request should be retried.

Classifies errors into retryable vs non-retryable categories, and
provides backoff delay calculation with optional jitter.

Rules (hardcoded, auditable):
  - 429 (rate limit) → retryable, extended backoff
  - 5xx (server error) → retryable
  - timeout / network errors → retryable
  - 401/403 (auth/forbidden) → NOT retryable
  - 404 (not found) → NOT retryable
  - 400/402/405-428 → NOT retryable (client errors except 429)
  - parser errors → conditionally retryable

Usage:
    from acs.scheduler.retry_policy import RetryPolicy

    policy = RetryPolicy(max_retries=3)
    should, delay = policy.should_retry(status_code=429, retry_count=1)
    if should:
        time.sleep(delay)
"""

from dataclasses import dataclass, field
from typing import Optional, Tuple
import random
import time


# ── Retryable / non-retryable status codes ───────────────────────

# Status codes that should ALWAYS be retried
_RETRYABLE_STATUS_CODES: set = {
    429,  # Too Many Requests
    500,  # Internal Server Error
    502,  # Bad Gateway
    503,  # Service Unavailable
    504,  # Gateway Timeout
}

# Status codes that should NEVER be retried
_NON_RETRYABLE_STATUS_CODES: set = {
    400,  # Bad Request
    401,  # Unauthorized
    402,  # Payment Required
    403,  # Forbidden
    404,  # Not Found
    405,  # Method Not Allowed
    406,  # Not Acceptable
    407,  # Proxy Authentication Required
    408,  # Request Timeout — retryable in principle, but urllib handles it
    409,  # Conflict
    410,  # Gone
    411,  # Length Required
    412,  # Precondition Failed
    413,  # Payload Too Large
    414,  # URI Too Long
    415,  # Unsupported Media Type
    416,  # Range Not Satisfiable
    417,  # Expectation Failed
    418,  # I'm a teapot
    421,  # Misdirected Request
    422,  # Unprocessable Entity
    423,  # Locked
    424,  # Failed Dependency
    425,  # Too Early
    426,  # Upgrade Required
    428,  # Precondition Required
    431,  # Request Header Fields Too Large
    451,  # Unavailable For Legal Reasons
}

# Error category indicators (regex patterns matched against error text)
_RETRYABLE_ERROR_PATTERNS = [
    "timeout", "timed out", "超时",
    "connection refused", "connection reset",
    "connection aborted",
    "name resolution", "dns", "getaddrinfo",
    "network", "unreachable", "socket",
    "too many requests", "rate limit",
]

_NON_RETRYABLE_ERROR_PATTERNS = [
    "404", "not found",
    "401", "unauthorized",
    "403", "forbidden",
    "access denied", "blocked",
]


@dataclass
class RetryDecision:
    """The result of a retry check."""

    should_retry: bool = False
    delay_seconds: float = 0.0
    reason: str = ""
    retry_count: int = 0
    max_retries: int = 3

    def to_dict(self) -> dict:
        return {
            "should_retry": self.should_retry,
            "delay_seconds": self.delay_seconds,
            "reason": self.reason,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
        }


class RetryPolicy:
    """Determines retry eligibility and calculates backoff delays.

    Args:
        max_retries: Maximum retry attempts per URL
        backoff_base: Base delay in seconds (multiplied by 2^retry_count)
        jitter_enabled: Add random jitter (±25%) to delay
        retry_on_4xx: If True, also retry non-429 4xx errors (NOT recommended)
    """

    # Known 429-specific delays — Retry-After header is respected if present
    DEFAULT_429_DELAY = 30.0

    def __init__(
        self,
        max_retries: int = 3,
        backoff_base: float = 1.5,
        jitter_enabled: bool = True,
        retry_on_4xx: bool = False,
    ):
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.jitter_enabled = jitter_enabled
        self.retry_on_4xx = retry_on_4xx

    # ── Public API ───────────────────────────────────────────────

    def should_retry(
        self,
        retry_count: int,
        status_code: int = 0,
        error_text: str = "",
        retry_after: Optional[float] = None,
    ) -> RetryDecision:
        """Decide whether to retry a failed request.

        Args:
            retry_count: How many retries have already been attempted
            status_code: HTTP status code (0 for network-level errors)
            error_text: Exception message or error description
            retry_after: Value of Retry-After header (seconds), if present

        Returns:
            RetryDecision with should_retry and delay_seconds
        """
        # ── Hard limit ──
        if retry_count >= self.max_retries:
            return RetryDecision(
                should_retry=False,
                delay_seconds=0.0,
                reason=f"Max retries ({self.max_retries}) exhausted",
                retry_count=retry_count,
                max_retries=self.max_retries,
            )

        # ── Status-code based ──
        should, reason, base_delay = self._classify_by_status(status_code, retry_after)
        if should is not None:
            if not should:
                return RetryDecision(
                    should_retry=False, delay_seconds=0.0,
                    reason=reason, retry_count=retry_count,
                    max_retries=self.max_retries,
                )
            delay = self._compute_delay(retry_count, base_delay)
            return RetryDecision(
                should_retry=True, delay_seconds=delay,
                reason=reason, retry_count=retry_count,
                max_retries=self.max_retries,
            )

        # ── Error-text based (for status_code=0 or unknown) ──
        should, reason = self._classify_by_error_text(error_text)
        if not should:
            return RetryDecision(
                should_retry=False, delay_seconds=0.0,
                reason=reason, retry_count=retry_count,
                max_retries=self.max_retries,
            )

        delay = self._compute_delay(retry_count, 0.0)
        return RetryDecision(
            should_retry=True, delay_seconds=delay,
            reason=reason, retry_count=retry_count,
            max_retries=self.max_retries,
        )

    def classify_error(self, error_text: str) -> str:
        """Classify an error as 'retryable' or 'non_retryable'."""
        should, _ = self._classify_by_error_text(error_text)
        return "retryable" if should else "non_retryable"

    # ── Internals ────────────────────────────────────────────────

    def _classify_by_status(
        self, status_code: int, retry_after: Optional[float]
    ) -> Tuple[Optional[bool], str, float]:
        """Returns (should_retry, reason, base_delay_override). None = status unknown, use text."""
        if status_code == 0:
            return None, "", 0.0

        if status_code in _RETRYABLE_STATUS_CODES:
            if status_code == 429:
                delay = retry_after if retry_after else self.DEFAULT_429_DELAY
                return True, f"HTTP {status_code} — rate limited", delay
            return True, f"HTTP {status_code} — server error (retryable)", 0.0

        if status_code in _NON_RETRYABLE_STATUS_CODES:
            if status_code == 404:
                return False, f"HTTP 404 — not found (not retryable)", 0.0
            if status_code in (401, 403):
                return False, f"HTTP {status_code} — auth/forbidden (not retryable)", 0.0
            return False, f"HTTP {status_code} — client error (not retryable)", 0.0

        # Unknown status code — classify by range
        if 500 <= status_code < 600:
            return True, f"HTTP {status_code} — server error (retryable)", 0.0
        if 400 <= status_code < 500:
            if self.retry_on_4xx:
                return True, f"HTTP {status_code} — client error (retry_on_4xx enabled)", 0.0
            return False, f"HTTP {status_code} — client error (not retryable)", 0.0

        return None, "", 0.0

    def _classify_by_error_text(self, error_text: str) -> Tuple[bool, str]:
        """Classify based on error message content."""
        if not error_text:
            return False, "Unknown error — defaulting to no retry"

        error_lower = error_text.lower()

        # Non-retryable patterns first (take priority)
        for pat in _NON_RETRYABLE_ERROR_PATTERNS:
            if pat in error_lower:
                if "404" in pat or "not found" in pat:
                    return False, "404 / not found (not retryable)"
                if "401" in pat or "unauthorized" in pat:
                    return False, "401 / unauthorized (not retryable)"
                if "403" in pat or "forbidden" in pat:
                    return False, "403 / forbidden (not retryable)"
                return False, f"Non-retryable error: {pat}"

        # Retryable patterns
        for pat in _RETRYABLE_ERROR_PATTERNS:
            if pat in error_lower:
                return True, f"Retryable error: {pat}"

        return False, "Unknown error type — defaulting to no retry"

    def _compute_delay(self, retry_count: int, base_delay_override: float = 0.0) -> float:
        """Calculate backoff delay with optional jitter."""
        if base_delay_override > 0:
            base = base_delay_override
        else:
            base = self.backoff_base * (2 ** retry_count)

        # Clamp
        base = min(base, 120.0)

        if self.jitter_enabled:
            jitter = random.uniform(-0.25, 0.25) * base
            return max(0.1, base + jitter)

        return base
