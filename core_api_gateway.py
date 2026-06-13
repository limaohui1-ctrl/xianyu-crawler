"""
Unified cloud API request gateway — all external HTTP calls MUST go through this layer.

Protections provided:
  - Exponential backoff retry with jitter (prevents thundering herd)
  - Rate limiting: global + per-domain (token bucket)
  - Circuit breaker: CLOSED → OPEN → HALF_OPEN (prevents hammering dead APIs)
  - Concurrency control (bounded semaphore)
  - Error classification (4xx/client vs 5xx/server vs rate-limit vs network)
  - Request tracing (trace_id for observability — Phase 3 hook)
  - Thread-safe (all state guarded by locks)

Usage:
    from core_api_gateway import get_gateway

    gateway = get_gateway()
    data = gateway.request_json("POST", url, payload=payload, headers=headers, timeout=60)
"""

import hashlib
import json
import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


# ═══════════════════════════════════════════════════════════════════
# Error Classification
# ═══════════════════════════════════════════════════════════════════

def classify_http_status(code: int) -> str:
    """Classify HTTP status into an actionable category string."""
    if code < 0:
        return "NETWORK_ERROR"
    if code < 200:
        return "INFORMATIONAL"
    if code < 300:
        return "SUCCESS"
    if code == 429:
        return "RATE_LIMITED"
    if code < 500:
        return "CLIENT_ERROR"
    return "SERVER_ERROR"


def is_retryable_status(code: int) -> bool:
    """Return True when this HTTP status warrants a retry."""
    return code in {429, 502, 503, 504} or (code >= 500 and code < 600)


def retry_after_seconds(headers: dict, default: float = 5.0) -> float:
    """Extract Retry-After value from response headers, with a fallback."""
    raw = str(headers.get("Retry-After", "")).strip()
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return default


# ═══════════════════════════════════════════════════════════════════
# Retry Config
# ═══════════════════════════════════════════════════════════════════

@dataclass
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 1.0        # seconds — first backoff interval
    max_delay: float = 30.0        # seconds — cap
    jitter: bool = True            # add random jitter to spread retries
    retry_on_timeout: bool = True
    retry_on_network_error: bool = True


def compute_backoff(attempt: int, config: RetryConfig) -> float:
    """Exponential backoff: min(base * 2^attempt, max_delay).

    When jitter is enabled the result is multiplied by (0.5 + random),
    so two workers hitting the same API don't synchronise their retries.
    """
    delay = min(config.base_delay * (2 ** attempt), config.max_delay)
    if config.jitter:
        delay *= 0.5 + random.random()
    return delay


# ═══════════════════════════════════════════════════════════════════
# Token Bucket Rate Limiter
# ═══════════════════════════════════════════════════════════════════

class TokenBucketRateLimiter:
    """Thread-safe token-bucket rate limiter.

    Tokens refill at ``rate`` per second; bucket capacity is ``capacity``.
    Each request consumes one token.  Callers block (with timeout) when no
    token is available.
    """

    def __init__(self, rate: float = 10.0, capacity: Optional[float] = None):
        self.rate = float(rate)
        self.capacity = float(capacity if capacity is not None else rate)
        self.tokens = self.capacity
        self.last_refill = time.monotonic()
        self.lock = threading.Lock()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now

    def acquire(self, timeout: float = 30.0) -> bool:
        """Block until a token is available or *timeout* expires.

        Returns True when a token was acquired, False on timeout."""
        deadline = time.monotonic() + timeout
        while True:
            with self.lock:
                self._refill()
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            wait = max(0.01, min(0.2, remaining, (1.0 - self.tokens) / max(self.rate, 0.1)))
            time.sleep(wait)


class DomainRateLimiter:
    """Per-domain token-bucket map.  Missing domains get a bucket at *default_rps*."""

    def __init__(self, default_rps: float = 5.0):
        self.default_rps = float(default_rps)
        self._buckets: Dict[str, TokenBucketRateLimiter] = {}
        self._lock = threading.Lock()

    def get(self, domain: str) -> TokenBucketRateLimiter:
        domain = domain.lower()
        with self._lock:
            if domain not in self._buckets:
                self._buckets[domain] = TokenBucketRateLimiter(rate=self.default_rps)
            return self._buckets[domain]


# ═══════════════════════════════════════════════════════════════════
# Circuit Breaker
# ═══════════════════════════════════════════════════════════════════

class CircuitState:
    CLOSED = "CLOSED"          # normal — requests pass through
    OPEN = "OPEN"              # tripped — requests fail fast
    HALF_OPEN = "HALF_OPEN"    # probing — limited requests allowed to test recovery


class CircuitBreaker:
    """Thread-safe circuit breaker.

    State machine:
      CLOSED  ──(failures >= threshold)──▶ OPEN
      OPEN    ──(recovery_timeout elapsed)──▶ HALF_OPEN
      HALF_OPEN ──(success)──▶ CLOSED
      HALF_OPEN ──(any failure)──▶ OPEN
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_probe_count: int = 1,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_probe_count = half_open_probe_count
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.half_open_probes = 0
        self.lock = threading.Lock()

    def allow_request(self) -> bool:
        """Check whether a request may proceed.  Call before every request."""
        with self.lock:
            if self.state == CircuitState.CLOSED:
                return True
            if self.state == CircuitState.OPEN:
                if time.monotonic() - self.last_failure_time >= self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_probes = 0
                    return True
                return False
            # HALF_OPEN — allow limited probe requests
            if self.half_open_probes < self.half_open_probe_count:
                self.half_open_probes += 1
                return True
            return False

    def record_success(self):
        with self.lock:
            self.failure_count = 0
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.CLOSED

    def record_failure(self):
        with self.lock:
            self.failure_count += 1
            self.last_failure_time = time.monotonic()
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN

    @property
    def status(self) -> dict:
        with self.lock:
            return {
                "state": self.state,
                "failure_count": self.failure_count,
                "last_failure_time": self.last_failure_time,
            }


# ═══════════════════════════════════════════════════════════════════
# Gateway Config
# ═══════════════════════════════════════════════════════════════════

@dataclass
class GatewayConfig:
    retry: RetryConfig = field(default_factory=RetryConfig)
    global_rps: float = 10.0
    per_domain_rps: float = 5.0
    circuit_breaker_enabled: bool = True
    cb_failure_threshold: int = 5
    cb_recovery_timeout: float = 30.0
    max_concurrency: int = 20
    default_timeout: int = 60
    enable_tracing: bool = True

    @classmethod
    def from_dict(cls, source: Optional[dict] = None) -> "GatewayConfig":
        source = source or {}
        retry = RetryConfig(
            max_retries=int(source.get("max_retries", 3)),
            base_delay=float(source.get("retry_base_delay", 1.0)),
            max_delay=float(source.get("retry_max_delay", 30.0)),
            jitter=bool(source.get("retry_jitter", True)),
            retry_on_timeout=bool(source.get("retry_on_timeout", True)),
            retry_on_network_error=bool(source.get("retry_on_network_error", True)),
        )
        return cls(
            retry=retry,
            global_rps=float(source.get("global_rps", 10.0)),
            per_domain_rps=float(source.get("per_domain_rps", 5.0)),
            circuit_breaker_enabled=bool(source.get("circuit_breaker_enabled", True)),
            cb_failure_threshold=int(source.get("cb_failure_threshold", 5)),
            cb_recovery_timeout=float(source.get("cb_recovery_timeout", 30.0)),
            max_concurrency=int(source.get("max_concurrency", 20)),
            default_timeout=int(source.get("timeout_seconds", 60)),
            enable_tracing=bool(source.get("enable_tracing", True)),
        )

    def to_dict(self) -> dict:
        return {
            "max_retries": self.retry.max_retries,
            "retry_base_delay": self.retry.base_delay,
            "retry_max_delay": self.retry.max_delay,
            "retry_jitter": self.retry.jitter,
            "retry_on_timeout": self.retry.retry_on_timeout,
            "retry_on_network_error": self.retry.retry_on_network_error,
            "global_rps": self.global_rps,
            "per_domain_rps": self.per_domain_rps,
            "circuit_breaker_enabled": self.circuit_breaker_enabled,
            "cb_failure_threshold": self.cb_failure_threshold,
            "cb_recovery_timeout": self.cb_recovery_timeout,
            "max_concurrency": self.max_concurrency,
            "timeout_seconds": self.default_timeout,
            "enable_tracing": self.enable_tracing,
        }


# ═══════════════════════════════════════════════════════════════════
# GatewayError — distinguishable from raw HTTP / network exceptions
# ═══════════════════════════════════════════════════════════════════

class GatewayError(RuntimeError):
    """Raised by ApiGateway when a request fails after all protections are
    exhausted.  Carries extra diagnostic fields."""
    def __init__(self, message: str, *, status_code: int = -1,
                 category: str = "", retries_attempted: int = 0,
                 domain: str = "", trace_id: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.category = category          # NETWORK_ERROR | RATE_LIMITED | SERVER_ERROR | CLIENT_ERROR
        self.retries_attempted = retries_attempted
        self.domain = domain
        self.trace_id = trace_id


# ═══════════════════════════════════════════════════════════════════
# Trace context (thread-local — Phase 3 hooks into this)
# ═══════════════════════════════════════════════════════════════════

class _TraceContext(threading.local):
    def __init__(self):
        self.trace_id = ""


_trace_ctx = _TraceContext()


def generate_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def current_trace_id() -> str:
    return _trace_ctx.trace_id


# ═══════════════════════════════════════════════════════════════════
# ApiGateway
# ═══════════════════════════════════════════════════════════════════

class ApiGateway:
    """Unified API request gateway — all external HTTP must go through here.

    Provides:
      - Exponential-backoff retry with jitter
      - Rate limiting (global + per-domain token buckets)
      - Circuit breaker per domain (CLOSED → OPEN → HALF_OPEN)
      - Bounded concurrency (semaphore)
      - Trace ID generation (for future observability)
      - Request statistics

    Thread-safe — multiple Qt workers / threads may share one gateway.
    """

    def __init__(self, config: Optional[GatewayConfig] = None):
        self.config = config or GatewayConfig()
        self.global_limiter = TokenBucketRateLimiter(
            rate=self.config.global_rps,
            capacity=self.config.global_rps * 2,
        )
        self.domain_limiter = DomainRateLimiter(
            default_rps=self.config.per_domain_rps,
        )
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._breakers_lock = threading.Lock()
        self._concurrency = threading.BoundedSemaphore(self.config.max_concurrency)
        self._stats: Dict[str, int] = {
            "total": 0, "ok": 0, "failed": 0,
            "rate_waits": 0, "cb_rejects": 0, "retries": 0,
        }
        self._stats_lock = threading.Lock()

    # ── Circuit breaker helpers ──────────────────────────────────

    def _breaker_for(self, domain: str) -> Optional[CircuitBreaker]:
        if not self.config.circuit_breaker_enabled:
            return None
        domain = domain.lower()
        with self._breakers_lock:
            if domain not in self._breakers:
                self._breakers[domain] = CircuitBreaker(
                    failure_threshold=self.config.cb_failure_threshold,
                    recovery_timeout=self.config.cb_recovery_timeout,
                )
            return self._breakers[domain]

    # ── Core request ─────────────────────────────────────────────

    def request(
        self,
        method: str,
        url: str,
        payload: Optional[dict] = None,
        headers: Optional[dict] = None,
        timeout: Optional[int] = None,
        trace_id: Optional[str] = None,
    ) -> str:
        """Execute an HTTP request with full retry / rate-limit / circuit-breaker
        protection.

        Returns the response body as a UTF-8 string.
        Raises ``GatewayError`` when all retries are exhausted or the request
        is rejected by a protection layer.

        Parameters
        ----------
        method : str
            HTTP method (GET, POST, DELETE, …).
        url : str
            Full request URL.
        payload : dict | None
            JSON-serialisable body.  ``None`` means no body.
        headers : dict | None
            Extra headers.  ``Content-Type: application/json`` is set
            automatically when *payload* is provided (unless already present).
        timeout : int | None
            Per-request timeout in seconds.  Falls back to ``config.default_timeout``.
        trace_id : str | None
            Trace ID for observability.  Auto-generated when *config.enable_tracing*
            is True and no value is supplied.
        """
        # ── Prepare ────────────────────────────────────────────
        timeout = timeout if timeout is not None else self.config.default_timeout
        headers = dict(headers or {})
        body_bytes: Optional[bytes] = None
        if isinstance(payload, bytes):
            body_bytes = payload  # raw bytes (multipart, etc.) — caller sets Content-Type
        elif payload is not None:
            body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")

        parsed = urlparse(url)
        domain = (parsed.hostname or "unknown").lower()

        if trace_id is None and self.config.enable_tracing:
            trace_id = generate_trace_id()

        self._stat_inc("total")

        # ── Rate limiting ───────────────────────────────────────
        if not self.global_limiter.acquire(timeout=30):
            raise GatewayError(
                "API网关：全局限流等待超时（当前 QPS 过高，请稍后重试）",
                category="RATE_LIMITED", domain=domain, trace_id=trace_id or "",
            )
        self._stat_inc("rate_waits")

        if not self.domain_limiter.get(domain).acquire(timeout=30):
            raise GatewayError(
                f"API网关：域名限流等待超时（{domain} 请求过于频繁）",
                category="RATE_LIMITED", domain=domain, trace_id=trace_id or "",
            )

        # ── Circuit breaker ─────────────────────────────────────
        breaker = self._breaker_for(domain)
        if breaker is not None and not breaker.allow_request():
            self._stat_inc("cb_rejects")
            raise GatewayError(
                f"API网关：熔断器已打开（{domain} 连续失败过多，{self.config.cb_recovery_timeout}s 后自动恢复）",
                category="CIRCUIT_OPEN", domain=domain, trace_id=trace_id or "",
            )

        # ── Concurrency semaphore ───────────────────────────────
        if not self._concurrency.acquire(timeout=timeout + 5):
            raise GatewayError(
                f"API网关：并发已满（max={self.config.max_concurrency}），请求被拒绝",
                category="CONCURRENCY_EXHAUSTED", domain=domain, trace_id=trace_id or "",
            )

        last_error: Optional[Exception] = None
        status_code: int = -1
        category: str = ""
        retries_attempted: int = 0

        try:
            for attempt in range(max(1, self.config.retry.max_retries)):
                try:
                    result_text = self._single_http(method, url, body_bytes, headers, timeout)
                    # ── Success ──
                    self._stat_inc("ok")
                    if breaker is not None:
                        breaker.record_success()
                    return result_text
                except HTTPError as exc:
                    last_error = exc
                    status_code = exc.code
                    category = classify_http_status(exc.code)
                    if not is_retryable_status(exc.code):
                        # 4xx (except 429) — don't retry
                        if breaker is not None:
                            breaker.record_failure()
                        raise _gateway_error_from_http(
                            exc, category=category, domain=domain,
                            retries=retries_attempted, trace_id=trace_id or "",
                        )
                    # 5xx / 429 — retryable
                    retries_attempted += 1
                    if attempt + 1 < self.config.retry.max_retries:
                        delay = compute_backoff(attempt, self.config.retry)
                        if exc.code == 429:
                            delay = max(delay, retry_after_seconds(dict(exc.headers), 5.0))
                        self._stat_inc("retries")
                        time.sleep(delay)
                        continue
                    # exhausted
                    if breaker is not None:
                        breaker.record_failure()
                    raise _gateway_error_from_http(
                        exc, category=category, domain=domain,
                        retries=retries_attempted, trace_id=trace_id or "",
                    )
                except (URLError, TimeoutError, OSError, ConnectionError) as exc:
                    last_error = exc
                    status_code = -1
                    category = classify_http_status(-1)
                    is_timeout = isinstance(exc, TimeoutError) or (
                        isinstance(exc, URLError) and "timed out" in str(exc).lower()
                    )
                    if is_timeout and not self.config.retry.retry_on_timeout:
                        if breaker is not None:
                            breaker.record_failure()
                        raise GatewayError(
                            f"API请求超时（重试已禁用）：{exc}",
                            category="NETWORK_ERROR", domain=domain,
                            trace_id=trace_id or "",
                        ) from exc
                    if isinstance(exc, (URLError, OSError, ConnectionError)):
                        if not self.config.retry.retry_on_network_error:
                            if breaker is not None:
                                breaker.record_failure()
                            raise GatewayError(
                                f"API网络错误（重试已禁用）：{exc}",
                                category="NETWORK_ERROR", domain=domain,
                                trace_id=trace_id or "",
                            ) from exc
                    retries_attempted += 1
                    if attempt + 1 < self.config.retry.max_retries:
                        self._stat_inc("retries")
                        time.sleep(compute_backoff(attempt, self.config.retry))
                        continue
                    if breaker is not None:
                        breaker.record_failure()
                    raise GatewayError(
                        f"API网络连接失败（已重试{retries_attempted}次）：{exc}",
                        status_code=-1, category="NETWORK_ERROR",
                        domain=domain, retries_attempted=retries_attempted,
                        trace_id=trace_id or "",
                    ) from exc

            # Should be unreachable — safety net
            if breaker is not None:
                breaker.record_failure()
            raise GatewayError(
                f"API请求失败（所有重试已用尽）：{last_error}",
                status_code=status_code, category=category or "UNKNOWN",
                domain=domain, retries_attempted=retries_attempted,
                trace_id=trace_id or "",
            )
        finally:
            self._concurrency.release()

    def _single_http(self, method: str, url: str, body: Optional[bytes],
                     headers: dict, timeout: int) -> str:
        """Issue one HTTP request — NO retry, NO rate-limit, NO circuit-breaker."""
        request = Request(url, data=body, headers=headers, method=method)
        with urlopen(request, timeout=timeout) as response:
            data = response.read()
            # urlopen raises HTTPError for codes >= 400,
            # so here we always have 2xx.
            return data.decode("utf-8", errors="replace")

    def request_json(
        self,
        method: str,
        url: str,
        payload: Optional[dict] = None,
        headers: Optional[dict] = None,
        timeout: Optional[int] = None,
    ) -> dict:
        """Execute *request()* and parse the response body as JSON.

        Returns an empty dict when the body is empty / whitespace-only
        (matching the historical behaviour of AIClient.request_json)."""
        text = self.request(method, url, payload, headers, timeout)
        if not text or not text.strip():
            return {}
        return json.loads(text)

    # ── Statistics ──────────────────────────────────────────────

    def _stat_inc(self, key: str):
        with self._stats_lock:
            self._stats[key] = self._stats.get(key, 0) + 1

    def get_stats(self) -> Dict[str, int]:
        with self._stats_lock:
            return dict(self._stats)

    def reset_stats(self):
        with self._stats_lock:
            for key in self._stats:
                self._stats[key] = 0

    def diagnostic_summary(self) -> dict:
        """Return a human-readable diagnostic snapshot for UI / logs."""
        breakers = {}
        with self._breakers_lock:
            for dom, cb in self._breakers.items():
                breakers[dom] = cb.status
        return {
            "stats": self.get_stats(),
            "circuit_breakers": breakers,
            "config": self.config.to_dict(),
        }


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _gateway_error_from_http(
    exc: HTTPError,
    *,
    category: str = "",
    domain: str = "",
    retries: int = 0,
    trace_id: str = "",
) -> GatewayError:
    """Build a GatewayError from an HTTPError with the response body as detail."""
    try:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
    except Exception:
        detail = str(exc)
    return GatewayError(
        f"API 请求失败：HTTP {exc.code} {detail}",
        status_code=exc.code,
        category=category or classify_http_status(exc.code),
        domain=domain,
        retries_attempted=retries,
        trace_id=trace_id,
    )


# ═══════════════════════════════════════════════════════════════════
# Global singleton
# ═══════════════════════════════════════════════════════════════════

_default_gateway: Optional[ApiGateway] = None
_default_gateway_lock = threading.Lock()


def get_gateway(config: Optional[GatewayConfig] = None) -> ApiGateway:
    """Return the process-wide singleton ApiGateway, creating it on first call."""
    global _default_gateway
    if _default_gateway is None:
        with _default_gateway_lock:
            if _default_gateway is None:
                _default_gateway = ApiGateway(config=config)
    return _default_gateway


def reset_gateway():
    """Reset the global gateway (for tests)."""
    global _default_gateway
    with _default_gateway_lock:
        _default_gateway = None
