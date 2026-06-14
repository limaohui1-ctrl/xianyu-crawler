"""
Checkpoint — save/restore crawl progress for resumability.

When a crawl is interrupted (crash, user stop, power loss), the checkpoint
allows resuming from the last saved position rather than starting over.

Checkpoint data is stored as JSON files in a local directory.  Each checkpoint
contains:
  - URLs processed / failed / remaining
  - Last successfully processed URL
  - Error summary
  - Configuration snapshot
  - Timestamp

Design: single-writer, atomic writes (write to .tmp then rename).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import json
import os
import threading
import time


@dataclass
class CheckpointState:
    """A snapshot of crawl progress at a point in time."""

    run_id: str = ""                        # unique run identifier
    status: str = "running"                 # running | paused | completed | failed
    urls_total: int = 0
    urls_processed: int = 0
    urls_failed: int = 0
    last_url: str = ""
    last_checkpoint_at: str = ""
    elapsed_seconds: float = 0.0
    processed_urls: List[str] = field(default_factory=list)   # last N processed (for audit)
    pending_urls: List[str] = field(default_factory=list)     # remaining URLs
    failed_urls: List[Dict[str, str]] = field(default_factory=list)  # [{"url":..., "error":...}]
    error_summary: Dict[str, str] = field(default_factory=dict)
    config_snapshot: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "urls_total": self.urls_total,
            "urls_processed": self.urls_processed,
            "urls_failed": self.urls_failed,
            "last_url": self.last_url,
            "last_checkpoint_at": self.last_checkpoint_at,
            "elapsed_seconds": self.elapsed_seconds,
            "processed_urls": self.processed_urls[-200:],     # keep last 200
            "pending_urls": self.pending_urls[:2000],         # keep first 2000
            "failed_urls": self.failed_urls[-100:],           # keep last 100
            "error_summary": dict(list(self.error_summary.items())[:50]),
            "config_snapshot": self.config_snapshot,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CheckpointState":
        return cls(
            run_id=str(data.get("run_id", "")),
            status=str(data.get("status", "running")),
            urls_total=int(data.get("urls_total", 0)),
            urls_processed=int(data.get("urls_processed", 0)),
            urls_failed=int(data.get("urls_failed", 0)),
            last_url=str(data.get("last_url", "")),
            last_checkpoint_at=str(data.get("last_checkpoint_at", "")),
            elapsed_seconds=float(data.get("elapsed_seconds", 0)),
            processed_urls=list(data.get("processed_urls", [])),
            pending_urls=list(data.get("pending_urls", [])),
            failed_urls=list(data.get("failed_urls", [])),
            error_summary=dict(data.get("error_summary", {})),
            config_snapshot=dict(data.get("config_snapshot", {})),
        )

    @property
    def progress_pct(self) -> float:
        if self.urls_total <= 0:
            return 0.0
        return round(self.urls_processed / self.urls_total * 100, 1)

    @property
    def can_resume(self) -> bool:
        return self.status == "running" and bool(self.pending_urls)


class CheckpointManager:
    """Manages crawl checkpoints for a single run.

    Saves progress to a JSON file at configurable intervals.  Supports
    resume by loading the last checkpoint and returning remaining URLs.

    Thread-safe for a single-writer pattern.

    Usage:
        mgr = CheckpointManager(checkpoint_dir=".checkpoints")
        mgr.init(urls=["http://..."], config={"template": "product"})
        for url in urls:
            process(url)
            mgr.record_progress(url)
        mgr.mark_completed()

    Resume:
        mgr = CheckpointManager(checkpoint_dir=".checkpoints")
        state = mgr.load_latest()
        if state and state.can_resume:
            remaining_urls = state.pending_urls
    """

    def __init__(self, checkpoint_dir: str = ".checkpoints",
                 save_interval: int = 10,
                 run_id: str = ""):
        self.checkpoint_dir = os.path.abspath(checkpoint_dir)
        self.save_interval = max(1, save_interval)
        self.run_id = run_id or f"run_{int(time.time())}"
        self._state: Optional[CheckpointState] = None
        self._lock = threading.Lock()
        self._counter = 0
        self._start_time = time.time()

    @property
    def checkpoint_file(self) -> str:
        return os.path.join(self.checkpoint_dir, f"{self.run_id}.json")

    @property
    def latest_file(self) -> str:
        return os.path.join(self.checkpoint_dir, "latest.json")

    # ── Init ──

    def init(self, urls: List[str], config: Optional[dict] = None):
        """Initialize a new run checkpoint."""
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        with self._lock:
            self._state = CheckpointState(
                run_id=self.run_id,
                status="running",
                urls_total=len(urls),
                pending_urls=list(urls),
                config_snapshot=dict(config or {}),
            )
            self._start_time = time.time()
            self._persist()

    # ── Progress ──

    def record_progress(self, url: str, failed: bool = False,
                        error_message: str = "",
                        pending_urls: Optional[List[str]] = None):
        """Record progress after processing one URL.

        Automatically persists at save_interval boundaries.
        """
        if self._state is None:
            raise RuntimeError("CheckpointManager not initialized. Call init() first.")

        with self._lock:
            state = self._state
            if failed:
                state.urls_failed += 1
                state.failed_urls.append({"url": url, "error": error_message[:500]})
                state.error_summary[url] = error_message[:200]
            state.urls_processed += 1
            state.last_url = url
            state.processed_urls.append(url)
            state.elapsed_seconds = round(time.time() - self._start_time, 1)

            if pending_urls is not None:
                state.pending_urls = list(pending_urls)
                state.urls_total = state.urls_processed + len(state.pending_urls)

            self._counter += 1
            if self._counter % self.save_interval == 0:
                self._persist()

    def record_error(self, url: str, error_message: str):
        """Record an error without incrementing progress counters."""
        if self._state is None:
            return
        with self._lock:
            self._state.error_summary[url] = error_message[:200]
            self._state.failed_urls.append({"url": url, "error": error_message[:500]})
            # Force save on error
            self._persist()

    # ── Lifecycle ──

    def mark_completed(self):
        """Mark the run as successfully completed."""
        if self._state is None:
            return
        with self._lock:
            self._state.status = "completed"
            self._state.elapsed_seconds = round(time.time() - self._start_time, 1)
            self._persist()

    def mark_failed(self, reason: str = ""):
        """Mark the run as failed."""
        if self._state is None:
            return
        with self._lock:
            self._state.status = "failed"
            if reason:
                self._state.error_summary["_fatal"] = reason[:500]
            self._state.elapsed_seconds = round(time.time() - self._start_time, 1)
            self._persist()

    def mark_paused(self):
        """Mark the run as paused (user requested)."""
        if self._state is None:
            return
        with self._lock:
            self._state.status = "paused"
            self._persist()

    def save(self):
        """Force an immediate save."""
        if self._state is None:
            return
        with self._lock:
            self._persist()

    # ── Resume ──

    def load_latest(self) -> Optional[CheckpointState]:
        """Load the latest checkpoint for this run_id, if it exists."""
        file_path = self.checkpoint_file
        if not os.path.exists(file_path):
            # Try latest.json
            file_path = self.latest_file
            if not os.path.exists(file_path):
                return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            state = CheckpointState.from_dict(data)
            # Verify it's still fresh — not too old
            if state.status == "running" and state.elapsed_seconds > 86400:
                # Stale checkpoint (>24h) — mark as failed
                pass
            return state
        except (json.JSONDecodeError, KeyError, OSError):
            return None

    def can_resume(self) -> bool:
        """Check if there's a resumable checkpoint."""
        state = self.load_latest()
        return state is not None and state.can_resume

    def resume_pending_urls(self) -> Optional[List[str]]:
        """Return remaining URLs from a recoverable checkpoint."""
        state = self.load_latest()
        if state and state.can_resume:
            return state.pending_urls
        return None

    # ── Query ──

    def get_state(self) -> Optional[CheckpointState]:
        """Return a copy of the current state."""
        if self._state is None:
            return None
        with self._lock:
            return CheckpointState.from_dict(self._state.to_dict())

    def get_progress(self) -> dict:
        """Return a lightweight progress dict."""
        if self._state is None:
            return {"status": "not_started"}
        with self._lock:
            return {
                "status": self._state.status,
                "processed": self._state.urls_processed,
                "failed": self._state.urls_failed,
                "total": self._state.urls_total,
                "progress_pct": self._state.progress_pct,
                "elapsed_seconds": self._state.elapsed_seconds,
                "last_url": self._state.last_url,
            }

    # ── Persistence ──

    def _persist(self):
        """Write checkpoint to disk.  Caller must hold _lock."""
        if self._state is None:
            return

        self._state.last_checkpoint_at = time.strftime("%Y-%m-%d %H:%M:%S")
        data = self._state.to_dict()

        # Atomic write: write to .tmp, then rename
        tmp_path = self.checkpoint_file + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.checkpoint_file)

            # Also write a "latest" symlink / copy
            latest_tmp = self.latest_file + ".tmp"
            with open(latest_tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(latest_tmp, self.latest_file)
        except OSError:
            pass  # Checkpoint save failure must not crash the crawl

    # ── Cleanup ──

    def delete(self):
        """Delete this run's checkpoint files."""
        for path in (self.checkpoint_file, self.latest_file):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
        with self._lock:
            self._state = None

    @staticmethod
    def list_checkpoints(checkpoint_dir: str = ".checkpoints") -> List[dict]:
        """List all checkpoint files in a directory, sorted by age."""
        if not os.path.isdir(checkpoint_dir):
            return []
        results = []
        for name in os.listdir(checkpoint_dir):
            if not name.endswith(".json"):
                continue
            path = os.path.join(checkpoint_dir, name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                results.append({
                    "run_id": data.get("run_id", name),
                    "status": data.get("status", "unknown"),
                    "processed": data.get("urls_processed", 0),
                    "total": data.get("urls_total", 0),
                    "last_checkpoint_at": data.get("last_checkpoint_at", ""),
                    "file": path,
                    "size_bytes": os.path.getsize(path),
                })
            except Exception:
                continue
        results.sort(key=lambda r: r.get("last_checkpoint_at", ""), reverse=True)
        return results
