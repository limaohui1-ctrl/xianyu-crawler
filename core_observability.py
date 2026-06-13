"""
Observability layer — request tracing, status logging, event state machine.

Provides:
  - Trace ID generation and propagation (thread-local)
  - Request/response event logging
  - Task state machine (PENDING → RUNNING → COMPLETED / FAILED / CANCELLED)
  - Per-run statistics aggregation
  - Diagnostic export for debugging

All writes are append-only to a JSONL diagnostic log file.
Integration: hooks into ApiGateway, AIClient, UniversalCollector.

Usage:
    from core_observability import TraceContext, log_event, TaskState

    with TraceContext("collect_urls") as ctx:
        ctx.log("url_start", url="https://...")
        result = do_work()
        ctx.log("url_done", url="https://...", ok=True)
"""

import json
import os
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════════
# Trace context (thread-local)
# ═══════════════════════════════════════════════════════════════════

class TraceContext:
    """Thread-local trace context.  Use as context manager or manually.

    with TraceContext("collect_urls", run_id=42):
        log_event("page_collected", url="https://...", ok=True)
    """

    _local = threading.local()

    def __init__(self, operation: str = "", run_id: int = 0,
                 parent_trace_id: str = ""):
        self.operation = operation
        self.trace_id = parent_trace_id or uuid.uuid4().hex[:16]
        self.span_id = uuid.uuid4().hex[:8]
        self.run_id = run_id
        self.started_at = time.time()
        self._previous: Optional[dict] = None

    def __enter__(self):
        self._previous = {
            "operation": getattr(self._local, "operation", ""),
            "trace_id": getattr(self._local, "trace_id", ""),
            "span_id": getattr(self._local, "span_id", ""),
            "run_id": getattr(self._local, "run_id", 0),
        }
        self._local.operation = self.operation
        self._local.trace_id = self.trace_id
        self._local.span_id = self.span_id
        self._local.run_id = self.run_id
        return self

    def __exit__(self, *args):
        if self._previous:
            self._local.operation = self._previous["operation"]
            self._local.trace_id = self._previous["trace_id"]
            self._local.span_id = self._previous["span_id"]
            self._local.run_id = self._previous["run_id"]

    @classmethod
    def current(cls) -> dict:
        """Return the current trace context as a dict (safe to serialize)."""
        return {
            "operation": getattr(cls._local, "operation", ""),
            "trace_id": getattr(cls._local, "trace_id", ""),
            "span_id": getattr(cls._local, "span_id", ""),
            "run_id": getattr(cls._local, "run_id", 0),
        }

    @classmethod
    def current_trace_id(cls) -> str:
        return getattr(cls._local, "trace_id", "")

    @classmethod
    def current_operation(cls) -> str:
        return getattr(cls._local, "operation", "")


# ═══════════════════════════════════════════════════════════════════
# Event logger
# ═══════════════════════════════════════════════════════════════════

_log_file: Optional[str] = None
_log_lock = threading.Lock()
_event_buffer: List[dict] = []
_buffer_max = 50


def _diagnostic_log_path() -> str:
    """Resolve the diagnostic log file path."""
    global _log_file
    if _log_file:
        return _log_file
    # Try the runtime path from universal_core, fall back to cwd
    try:
        from universal_core import runtime_diagnostic_log_file
        _log_file = runtime_diagnostic_log_file()
    except Exception:
        _log_file = os.path.join(os.getcwd(), "diagnostics.jsonl")
    os.makedirs(os.path.dirname(os.path.abspath(_log_file)), exist_ok=True)
    return _log_file


def log_event(event_type: str, **fields) -> str:
    """Log an observability event to the diagnostic log file.

    Automatically attaches trace context.

    Returns the event's trace_id for chaining.

    Example:
        log_event("api_call", provider="openai", model="gpt-5.2",
                  status_code=200, duration_ms=1234)
    """
    ctx = TraceContext.current()
    event = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ts_unix": time.time(),
        "event": event_type,
        "trace_id": ctx.get("trace_id", ""),
        "span_id": ctx.get("span_id", ""),
        "operation": ctx.get("operation", ""),
        "run_id": ctx.get("run_id", 0),
        **{k: _safe_value(v) for k, v in fields.items()},
    }

    with _log_lock:
        _event_buffer.append(event)
        if len(_event_buffer) >= _buffer_max:
            _flush_buffer()
        else:
            # Also flush on important events
            if event_type in {"task_done", "run_completed", "run_failed", "fatal_error"}:
                _flush_buffer()

    return ctx.get("trace_id", "")


def _safe_value(value: Any, max_len: int = 5000) -> Any:
    """Truncate large values for log safety."""
    if isinstance(value, str) and len(value) > max_len:
        return value[:max_len] + "..."
    if isinstance(value, (list, dict)):
        text = json.dumps(value, ensure_ascii=False, default=str)
        if len(text) > max_len:
            return text[:max_len] + "..."
    return value


def _flush_buffer():
    """Write buffered events to disk.  Caller must hold _log_lock."""
    if not _event_buffer:
        return
    path = _diagnostic_log_path()
    try:
        with open(path, "a", encoding="utf-8") as f:
            for event in _event_buffer:
                f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        _event_buffer.clear()
    except Exception:
        pass


def flush_events():
    """Force flush buffered events to disk (call before process exit)."""
    with _log_lock:
        _flush_buffer()


# ═══════════════════════════════════════════════════════════════════
# Task state machine
# ═══════════════════════════════════════════════════════════════════

class TaskState:
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"       # dedup / cache hit

    _VALID_TRANSITIONS = {
        PENDING: {QUEUED, RUNNING, SKIPPED, CANCELLED},
        QUEUED: {RUNNING, CANCELLED},
        RUNNING: {COMPLETED, FAILED, RETRYING, CANCELLED},
        RETRYING: {RUNNING, FAILED, CANCELLED},
        COMPLETED: set(),       # terminal
        FAILED: set(),          # terminal
        CANCELLED: set(),       # terminal
        SKIPPED: set(),         # terminal
    }

    @classmethod
    def can_transition(cls, from_state: str, to_state: str) -> bool:
        return to_state in cls._VALID_TRANSITIONS.get(from_state, set())

    @classmethod
    def is_terminal(cls, state: str) -> bool:
        return not cls._VALID_TRANSITIONS.get(state, set())


# ═══════════════════════════════════════════════════════════════════
# Run-level statistics aggregator
# ═══════════════════════════════════════════════════════════════════

@dataclass
class RunStats:
    """Aggregated statistics for a single crawl run."""
    run_id: int = 0
    urls_total: int = 0
    urls_completed: int = 0
    urls_failed: int = 0
    urls_skipped: int = 0
    api_calls: int = 0
    api_failures: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    retries: int = 0
    retry_successes: int = 0
    errors_by_category: Dict[str, int] = field(default_factory=dict)
    started_at: str = ""
    completed_at: str = ""
    total_duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "urls_total": self.urls_total,
            "urls_completed": self.urls_completed,
            "urls_failed": self.urls_failed,
            "urls_skipped": self.urls_skipped,
            "api_calls": self.api_calls,
            "api_failures": self.api_failures,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "retries": self.retries,
            "retry_successes": self.retry_successes,
            "errors_by_category": dict(self.errors_by_category),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_duration_ms": self.total_duration_ms,
        }


# ═══════════════════════════════════════════════════════════════════
# Observability facade
# ═══════════════════════════════════════════════════════════════════

class Observability:
    """High-level observability API that ties together tracing, logging,
    and statistics.

    Singleton — use `get_observability()`.
    """

    def __init__(self):
        self._runs: Dict[int, RunStats] = {}
        self._lock = threading.Lock()

    def start_run(self, run_id: int, urls_total: int = 0) -> TraceContext:
        with self._lock:
            self._runs[run_id] = RunStats(
                run_id=run_id,
                urls_total=urls_total,
                started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            )
        ctx = TraceContext("crawl_run", run_id=run_id)
        ctx.__enter__()
        log_event("run_started", run_id=run_id, urls_total=urls_total)
        return ctx

    def finish_run(self, run_id: int, *, failed: bool = False):
        with self._lock:
            stats = self._runs.get(run_id)
            if stats:
                stats.completed_at = time.strftime("%Y-%m-%d %H:%M:%S")
        log_event(
            "run_failed" if failed else "run_completed",
            run_id=run_id,
            stats=self.get_run_stats(run_id),
        )
        flush_events()

    def record_url_done(self, run_id: int, *, ok: bool = True,
                        skipped: bool = False, error_category: str = ""):
        with self._lock:
            stats = self._runs.get(run_id)
            if not stats:
                return
            if skipped:
                stats.urls_skipped += 1
            elif ok:
                stats.urls_completed += 1
            else:
                stats.urls_failed += 1
                if error_category:
                    stats.errors_by_category[error_category] = \
                        stats.errors_by_category.get(error_category, 0) + 1

    def record_api_call(self, run_id: int, *, ok: bool = True,
                        retry: bool = False):
        with self._lock:
            stats = self._runs.get(run_id)
            if not stats:
                return
            stats.api_calls += 1
            if not ok:
                stats.api_failures += 1
            if retry:
                stats.retries += 1

    def record_cache(self, run_id: int, *, hit: bool = True):
        with self._lock:
            stats = self._runs.get(run_id)
            if not stats:
                return
            if hit:
                stats.cache_hits += 1
            else:
                stats.cache_misses += 1

    def get_run_stats(self, run_id: int) -> Optional[dict]:
        with self._lock:
            stats = self._runs.get(run_id)
            return stats.to_dict() if stats else None

    def all_run_stats(self) -> List[dict]:
        with self._lock:
            return [s.to_dict() for s in self._runs.values()]


# ═══════════════════════════════════════════════════════════════════
# Global singleton
# ═══════════════════════════════════════════════════════════════════

_observability: Optional[Observability] = None
_obs_lock = threading.Lock()


def get_observability() -> Observability:
    global _observability
    if _observability is None:
        with _obs_lock:
            if _observability is None:
                _observability = Observability()
    return _observability
