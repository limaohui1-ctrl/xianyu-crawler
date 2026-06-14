"""
Structured logger — thread-safe logging with JSON lines output.

Provides:
  - File-based logging (JSONL format)
  - Console output with color-coded levels
  - Log levels: DEBUG, INFO, WARNING, ERROR
  - Automatic timestamp and PID tagging
  - Optional memory buffer for in-app display

Usage:
    from acs.observability.logger import get_logger

    logger = get_logger("crawler", log_file="crawl.log")
    logger.info("Starting crawl", urls=10, template="product")
    logger.warning("Slow response", url="...", elapsed=5.2)
    logger.error("Fetch failed", url="...", error="timeout")
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import json
import os
import sys
import threading
import time
import traceback


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


# Color codes for console output (Windows compatible via colorama if available)
_COLORS = {
    LogLevel.DEBUG: "\033[36m",    # cyan
    LogLevel.INFO: "\033[32m",     # green
    LogLevel.WARNING: "\033[33m",  # yellow
    LogLevel.ERROR: "\033[31m",    # red
}
_RESET = "\033[0m"


@dataclass
class LogEntry:
    """A single log entry."""
    timestamp: str = ""
    level: str = "INFO"
    logger: str = ""
    message: str = ""
    pid: int = 0
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        result = {
            "ts": self.timestamp,
            "level": self.level,
            "logger": self.logger,
            "msg": self.message,
            "pid": self.pid,
        }
        if self.data:
            result["data"] = self.data
        return result


class CrawlLogger:
    """Thread-safe structured logger for crawl operations.

    Args:
        name: Logger name (e.g., "fetcher", "parser", "main")
        log_file: Path to JSONL log file (None = console only)
        level: Minimum log level to record
        console: Enable console output
        buffer_size: Max entries in memory buffer (0 = no buffer)
    """

    def __init__(
        self,
        name: str = "crawler",
        log_file: Optional[str] = None,
        level: LogLevel = LogLevel.INFO,
        console: bool = True,
        buffer_size: int = 1000,
    ):
        self.name = name
        self.log_file = log_file
        self.level = level
        self.console = console
        self.buffer_size = buffer_size
        self._buffer: List[LogEntry] = []
        self._lock = threading.Lock()
        self._entry_count = 0

        # Ensure log directory exists
        if log_file:
            os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)

    # ── Public API ──

    def debug(self, message: str, **kwargs):
        self._log(LogLevel.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs):
        self._log(LogLevel.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._log(LogLevel.WARNING, message, **kwargs)

    def error(self, message: str, exc: Optional[Exception] = None, **kwargs):
        data = dict(kwargs)
        if exc:
            data["exception"] = str(exc)
            data["traceback"] = traceback.format_exc()
        self._log(LogLevel.ERROR, message, **data)

    # ── Core ──

    def _log(self, level: LogLevel, message: str, **data):
        """Record a log entry."""
        # Level filter
        level_order = {LogLevel.DEBUG: 0, LogLevel.INFO: 1, LogLevel.WARNING: 2, LogLevel.ERROR: 3}
        if level_order.get(level, 0) < level_order.get(self.level, 0):
            return

        entry = LogEntry(
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            level=level.value,
            logger=self.name,
            message=message,
            pid=os.getpid(),
            data=data,
        )

        with self._lock:
            self._entry_count += 1

            # Console output
            if self.console:
                self._write_console(entry)

            # File output
            if self.log_file:
                self._write_file(entry)

            # Memory buffer
            if self.buffer_size > 0:
                self._buffer.append(entry)
                if len(self._buffer) > self.buffer_size:
                    self._buffer = self._buffer[-self.buffer_size:]

    def _write_console(self, entry: LogEntry):
        """Write to stdout with color."""
        color = _COLORS.get(LogLevel(entry.level), "")
        ts = entry.timestamp[-8:]  # Just HH:MM:SS

        # Format extra data compactly
        extra = ""
        if entry.data:
            parts = []
            for k, v in entry.data.items():
                if k in ("traceback", "exception"):
                    continue
                if isinstance(v, str) and len(v) > 60:
                    v = v[:57] + "..."
                parts.append(f"{k}={v}")
            if parts:
                extra = " | " + " ".join(parts)

        line = f"{color}[{ts} {entry.level:7s}] {entry.message}{extra}{_RESET}"
        print(line, file=sys.stderr, flush=True)

    def _write_file(self, entry: LogEntry):
        """Append to JSONL log file."""
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        except OSError:
            pass

    # ── Queries ──

    @property
    def recent_entries(self) -> List[LogEntry]:
        """Return buffered log entries."""
        with self._lock:
            return list(self._buffer)

    @property
    def recent_errors(self) -> List[LogEntry]:
        """Return recent ERROR entries from buffer."""
        with self._lock:
            return [e for e in self._buffer if e.level == "ERROR"]

    @property
    def total_entries(self) -> int:
        return self._entry_count

    def clear_buffer(self):
        with self._lock:
            self._buffer.clear()

    # ── Context manager ──

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.error("Context exited with exception", exc=exc_val)


# ── Global logger registry ──────────────────────────────────────

_loggers: Dict[str, CrawlLogger] = {}
_logger_lock = threading.Lock()


def get_logger(name: str = "crawler", log_file: Optional[str] = None,
               level: LogLevel = LogLevel.INFO,
               console: bool = True) -> CrawlLogger:
    """Get or create a named logger.

    Loggers are cached by name.  Subsequent calls with the same name
    return the same instance.
    """
    with _logger_lock:
        if name in _loggers:
            return _loggers[name]
        logger = CrawlLogger(
            name=name,
            log_file=log_file,
            level=level,
            console=console,
        )
        _loggers[name] = logger
        return logger


def reset_loggers():
    """Clear the logger registry (useful for tests)."""
    with _logger_lock:
        _loggers.clear()
