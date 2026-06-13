"""
Task checkpoint — enables resume after interruption.

Saves crawl progress to the SQLite database at configurable intervals
so a stopped / crashed crawl can resume from the last checkpoint rather
than starting over.

Integration point: UniversalCollector.collect_urls() calls
checkpoint_save() every N URLs and checkpoint_resume() on startup.

Usage:
    from core_checkpoint import CheckpointManager

    cpm = CheckpointManager(database, run_id)
    cpm.save(processed_count, failed_count, last_url, pending_urls)

    # On resume:
    state = cpm.load()
    if state and state["status"] == "running":
        remaining_urls = state["pending_urls"]
"""

import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse


# ═══════════════════════════════════════════════════════════════════
# Checkpoint data model
# ═══════════════════════════════════════════════════════════════════

@dataclass
class CheckpointState:
    run_id: int = 0
    status: str = "running"              # running | paused | completed | failed
    urls_total: int = 0
    urls_processed: int = 0
    urls_failed: int = 0
    last_url: str = ""
    last_checkpoint_at: str = ""
    processed_urls: List[str] = field(default_factory=list)
    pending_urls: List[str] = field(default_factory=list)
    error_summary: Dict[str, str] = field(default_factory=dict)
    config_snapshot: Dict[str, Any] = field(default_factory=dict)
    # Incremental counter — used to decide when to write
    _checkpoint_count: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> "CheckpointState":
        return cls(
            run_id=int(data.get("run_id", 0)),
            status=str(data.get("status", "running")),
            urls_total=int(data.get("urls_total", 0)),
            urls_processed=int(data.get("urls_processed", 0)),
            urls_failed=int(data.get("urls_failed", 0)),
            last_url=str(data.get("last_url", "")),
            last_checkpoint_at=str(data.get("last_checkpoint_at", "")),
            processed_urls=list(data.get("processed_urls", [])),
            pending_urls=list(data.get("pending_urls", [])),
            error_summary=dict(data.get("error_summary", {})),
            config_snapshot=dict(data.get("config_snapshot", {})),
            _checkpoint_count=int(data.get("_checkpoint_count", 0)),
        )

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "urls_total": self.urls_total,
            "urls_processed": self.urls_processed,
            "urls_failed": self.urls_failed,
            "last_url": self.last_url,
            "last_checkpoint_at": self.last_checkpoint_at,
            "processed_urls": self.processed_urls[-200:],   # trim — keep last 200
            "pending_urls": self.pending_urls[:500],        # trim — keep first 500
            "error_summary": dict(list(self.error_summary.items())[:50]),
            "config_snapshot": self.config_snapshot,
            "_checkpoint_count": self._checkpoint_count,
        }


# ═══════════════════════════════════════════════════════════════════
# Checkpoint manager
# ═══════════════════════════════════════════════════════════════════

class CheckpointManager:
    """Manages crawl-state checkpoints in the collector SQLite database.

    Saves minimal state (progress counters, error summary, pending URLs)
    so a crawl can resume after interruption.  Does NOT duplicate the
    records table — already-saved records are the source of truth for
    per-URL data.

    Thread-safe — uses a lock so concurrent workers don't corrupt state.
    """

    # Table name in the collector database
    TABLE = "checkpoints"

    def __init__(self, database, run_id: int = 0,
                 save_interval: int = 5):
        """*database*: CollectorDatabase instance.
        *run_id*: current run ID.
        *save_interval*: save every N processed URLs (0 = manual only).
        """
        self.database = database
        self.run_id = int(run_id or 0)
        self.save_interval = max(1, int(save_interval))
        self._state = CheckpointState(run_id=self.run_id)
        self._lock = threading.Lock()
        self._ensure_table()

    # ── Table management ────────────────────────────────────────

    def _ensure_table(self):
        """Create the checkpoints table if it doesn't exist (idempotent)."""
        with self.database.connect() as conn:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE} (
                    run_id INTEGER PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                )
            """)

    # ── State management ────────────────────────────────────────

    def init(self, urls: List[str], config: Optional[dict] = None):
        """Initialise checkpoint for a new run."""
        with self._lock:
            self._state = CheckpointState(
                run_id=self.run_id,
                status="running",
                urls_total=len(urls),
                pending_urls=[self._normalize_url(u) for u in urls],
                config_snapshot=dict(config or {}),
            )
            self._persist()

    def record_progress(self, url: str, failed: bool = False,
                        pending_urls: Optional[List[str]] = None):
        """Call after processing one URL.  Auto-saves at *save_interval*.

        If *pending_urls* is provided it replaces the pending list (useful
        when the collector dynamically discovers new URLs)."""
        with self._lock:
            state = self._state
            if failed:
                state.urls_failed += 1
                state.error_summary[url] = state.error_summary.get(url, "") or "failed"
            state.urls_processed += 1
            state.last_url = url
            state.processed_urls.append(url)
            if pending_urls is not None:
                state.pending_urls = [self._normalize_url(u) for u in pending_urls]
                state.urls_total = state.urls_processed + len(state.pending_urls)
            state._checkpoint_count += 1
            if state._checkpoint_count % self.save_interval == 0:
                self._persist()

    def record_error(self, url: str, error_message: str):
        """Record a recoverable error without incrementing counters."""
        with self._lock:
            self._state.error_summary[url] = str(error_message)[:500]
            # Force save on error
            self._persist()

    def mark_completed(self):
        with self._lock:
            self._state.status = "completed"
            self._persist()

    def mark_failed(self, reason: str = ""):
        with self._lock:
            self._state.status = "failed"
            if reason:
                self._state.error_summary["_fatal"] = reason
            self._persist()

    # ── Resume ──────────────────────────────────────────────────

    def can_resume(self) -> bool:
        """Check whether a previous run exists and is resumable."""
        state = self._load_from_db()
        if state is None:
            return False
        return state.status == "running" and bool(state.pending_urls)

    def resume_state(self) -> Optional[CheckpointState]:
        """Load the last checkpoint.  Returns None if nothing to resume."""
        state = self._load_from_db()
        if state is None:
            return None
        if state.status == "running" and state.pending_urls:
            state.status = "resuming"
            state._checkpoint_count = 0
            return state
        return None

    def get_state(self) -> CheckpointState:
        """Return a copy of the current in-memory state."""
        with self._lock:
            return CheckpointState.from_dict(self._state.to_dict())

    # ── Persistence ─────────────────────────────────────────────

    def _persist(self):
        """Write current state to the database.  Caller must hold _lock."""
        state = self._state
        state.last_checkpoint_at = time.strftime("%Y-%m-%d %H:%M:%S")
        state_dict = state.to_dict()
        try:
            with self.database.connect() as conn:
                conn.execute(
                    f"""INSERT OR REPLACE INTO {self.TABLE}
                        (run_id, state_json, updated_at)
                        VALUES (?, ?, datetime('now','localtime'))""",
                    (self.run_id, json.dumps(state_dict, ensure_ascii=False)),
                )
        except Exception:
            # Checkpoint save failure must NOT crash the crawl
            pass

    def _load_from_db(self) -> Optional[CheckpointState]:
        """Load state from DB.  Returns None if not found or corrupted."""
        try:
            with self.database.connect() as conn:
                row = conn.execute(
                    f"SELECT state_json FROM {self.TABLE} WHERE run_id = ?",
                    (self.run_id,),
                ).fetchone()
            if row and row[0]:
                return CheckpointState.from_dict(json.loads(row[0]))
        except Exception:
            pass
        return None

    def save(self):
        """Force an immediate save (public API)."""
        with self._lock:
            self._persist()

    # ── Cleanup ─────────────────────────────────────────────────

    def delete(self):
        """Remove this run's checkpoint from the database."""
        try:
            with self.database.connect() as conn:
                conn.execute(
                    f"DELETE FROM {self.TABLE} WHERE run_id = ?",
                    (self.run_id,),
                )
        except Exception:
            pass

    @staticmethod
    def _normalize_url(url) -> str:
        if isinstance(url, str):
            return url
        return str(url)


# ═══════════════════════════════════════════════════════════════════
# URL dedup wrapper (lightweight in-memory + checkpoint-backed)
# ═══════════════════════════════════════════════════════════════════

class UrlDedupGuard:
    """Prevents re-scraping the same URL within a session + uses the
    URL dedup cache for cross-session dedup.

    Usage:
        guard = UrlDedupGuard()
        if guard.should_skip(url):
            continue  # already seen recently
        guard.mark_seen(url)
    """

    def __init__(self):
        self._seen: set = set()

    def should_skip(self, url: str) -> bool:
        key = self._normalize(url)
        if key in self._seen:
            return True
        # Also check cross-session cache
        from core_cache import get_url_dedup_cache, url_dedup_key
        if get_url_dedup_cache().has(url_dedup_key(key)):
            return True
        return False

    def mark_seen(self, url: str):
        key = self._normalize(url)
        self._seen.add(key)
        from core_cache import get_url_dedup_cache, url_dedup_key
        get_url_dedup_cache().set(url_dedup_key(key), True)

    def clear(self):
        self._seen.clear()

    @staticmethod
    def _normalize(url: str) -> str:
        """Strip fragments and common tracking params for dedup."""
        parsed = urlparse(url)
        # Remove fragment
        clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if parsed.query:
            clean += f"?{parsed.query}"
        return clean.lower()
