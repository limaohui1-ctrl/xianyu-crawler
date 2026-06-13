"""
Task data model — the canonical representation of a crawl task.

A task represents a single URL + configuration that the crawler will process.
It moves through a defined lifecycle: PENDING → RUNNING → COMPLETED / FAILED.

This model is decoupled from any UI or database layer — it's pure data.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
import uuid
import time


class TaskStatus(str, Enum):
    """Canonical task lifecycle states."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"  # e.g. already processed, dedup'd out


class FetchMode(str, Enum):
    """How to acquire the page content."""
    STATIC = "static"       # urllib / requests
    BROWSER = "browser"     # Playwright headless
    API = "api"             # direct API call (JSON endpoint)


class ParseMode(str, Enum):
    """Which parser strategy to use."""
    AUTO = "auto"           # let the engine decide
    CSS = "css"
    XPATH = "xpath"
    JSON = "json"
    JSONLD = "jsonld"
    FALLBACK = "fallback"


@dataclass
class TaskConfig:
    """Per-task configuration that controls fetch + parse behavior."""
    fetch_mode: FetchMode = FetchMode.STATIC
    parse_mode: ParseMode = ParseMode.AUTO
    timeout_seconds: int = 30
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    )
    max_retries: int = 3
    scroll_times: int = 0        # browser only
    keep_login_state: bool = False
    headers: Dict[str, str] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "fetch_mode": self.fetch_mode.value,
            "parse_mode": self.parse_mode.value,
            "timeout_seconds": self.timeout_seconds,
            "user_agent": self.user_agent,
            "max_retries": self.max_retries,
            "scroll_times": self.scroll_times,
            "keep_login_state": self.keep_login_state,
            "headers": dict(self.headers),
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaskConfig":
        return cls(
            fetch_mode=FetchMode(data.get("fetch_mode", "static")),
            parse_mode=ParseMode(data.get("parse_mode", "auto")),
            timeout_seconds=int(data.get("timeout_seconds", 30)),
            user_agent=str(data.get("user_agent", cls.user_agent)),
            max_retries=int(data.get("max_retries", 3)),
            scroll_times=int(data.get("scroll_times", 0)),
            keep_login_state=bool(data.get("keep_login_state", False)),
            headers=dict(data.get("headers", {})),
            extra=dict(data.get("extra", {})),
        )


@dataclass
class Task:
    """A crawl task — one URL to process with its configuration."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    url: str = ""
    template_name: str = "auto"
    config: TaskConfig = field(default_factory=TaskConfig)
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 5               # 0 = highest, 9 = lowest
    retry_count: int = 0
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error_message: str = ""
    error_category: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ── computed / cached ──

    @property
    def domain(self) -> str:
        try:
            return urlparse(self.url).netloc.lower()
        except Exception:
            return ""

    @property
    def is_terminal(self) -> bool:
        """Has the task reached a final state?"""
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.SKIPPED)

    @property
    def elapsed_seconds(self) -> Optional[float]:
        if self.started_at is None:
            return None
        end = self.completed_at or time.time()
        return round(end - self.started_at, 3)

    def mark_running(self):
        self.status = TaskStatus.RUNNING
        self.started_at = time.time()

    def mark_completed(self):
        self.status = TaskStatus.COMPLETED
        self.completed_at = time.time()

    def mark_failed(self, error: str = "", category: str = ""):
        self.status = TaskStatus.FAILED
        self.completed_at = time.time()
        self.error_message = error[:1000]
        self.error_category = category[:200]

    def mark_skipped(self, reason: str = ""):
        self.status = TaskStatus.SKIPPED
        self.completed_at = time.time()
        self.error_message = reason[:500]

    def can_retry(self) -> bool:
        """Check if retry is allowed."""
        if self.config.max_retries <= 0:
            return False
        return self.retry_count < self.config.max_retries

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "template_name": self.template_name,
            "config": self.config.to_dict(),
            "status": self.status.value,
            "priority": self.priority,
            "retry_count": self.retry_count,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "domain": self.domain,
            "error_message": self.error_message,
            "error_category": self.error_category,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        return cls(
            id=str(data.get("id", "")),
            url=str(data.get("url", "")),
            template_name=str(data.get("template_name", "auto")),
            config=TaskConfig.from_dict(data.get("config", {})),
            status=TaskStatus(data.get("status", "PENDING")),
            priority=int(data.get("priority", 5)),
            retry_count=int(data.get("retry_count", 0)),
            created_at=float(data.get("created_at", time.time())),
            started_at=float(data["started_at"]) if data.get("started_at") else None,
            completed_at=float(data["completed_at"]) if data.get("completed_at") else None,
            error_message=str(data.get("error_message", "")),
            error_category=str(data.get("error_category", "")),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class TaskBatch:
    """A group of tasks to process together, with aggregate status."""

    tasks: List[Task] = field(default_factory=list)
    batch_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    created_at: float = field(default_factory=time.time)

    @property
    def completed_count(self) -> int:
        return sum(1 for t in self.tasks if t.status == TaskStatus.COMPLETED)

    @property
    def failed_count(self) -> int:
        return sum(1 for t in self.tasks if t.status == TaskStatus.FAILED)

    @property
    def pending_count(self) -> int:
        return sum(1 for t in self.tasks if t.status == TaskStatus.PENDING)

    @property
    def is_done(self) -> bool:
        return all(t.is_terminal for t in self.tasks)

    @property
    def progress(self) -> dict:
        return {
            "total": len(self.tasks),
            "completed": self.completed_count,
            "failed": self.failed_count,
            "pending": self.pending_count,
        }
