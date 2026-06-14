"""
SQLite Dedup Store — persistent URL and content-hash deduplication.

Upgrades the in-memory DedupStore (acs/storage/dedup.py) with optional
SQLite persistence.  Falls back gracefully to in-memory store.

Supports:
  - URL normalisation and dedup
  - Content SHA256 hash dedup
  - TTL-based expiry
  - Cross-process / restart persistence
  - Atomic transactions
  - Statistics

Usage:
    from acs.storage.sqlite_dedup_store import SQLiteDedupStore

    store = SQLiteDedupStore(db_path="acs_data/dedup.db")
    if not store.is_duplicate_url("http://..."):
        store.mark_url("http://...")
"""

import hashlib
import os
import sqlite3
import threading
import time
from typing import Dict, List, Optional, Tuple


class SQLiteDedupStore:
    """Persistent URL and content-hash deduplication.

    Args:
        db_path: Path to SQLite database file.  None = in-memory only.
        ttl_seconds: How long before a dedup entry expires (0 = never)
    """

    def __init__(self, db_path: Optional[str] = "acs_data/dedup.db",
                 ttl_seconds: int = 0):
        self.db_path = db_path
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self):
        """Initialize the SQLite database and create tables."""
        if self.db_path:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        else:
            self._conn = sqlite3.connect(":memory:", check_same_thread=False)

        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")

        with self._lock:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS url_dedup (
                    normalized_url TEXT PRIMARY KEY,
                    original_url TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    hit_count INTEGER DEFAULT 1,
                    expires_at TEXT
                )
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS content_dedup (
                    content_hash TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    title TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    hit_count INTEGER DEFAULT 1,
                    expires_at TEXT
                )
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_url_expires
                ON url_dedup(expires_at)
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_content_expires
                ON content_dedup(expires_at)
            """)
            self._conn.commit()

    # ── URL dedup ────────────────────────────────────────────────

    def is_duplicate_url(self, url: str) -> bool:
        """Check if URL has already been seen (and not expired)."""
        norm = self._normalize_url(url)
        with self._lock:
            cur = self._conn.execute(
                "SELECT 1 FROM url_dedup WHERE normalized_url = ? AND "
                "(expires_at IS NULL OR expires_at > ?)",
                (norm, self._now_iso()),
            )
            return cur.fetchone() is not None

    def mark_url(self, url: str) -> bool:
        """Mark URL as seen. Returns True if newly marked, False if already exists."""
        norm = self._normalize_url(url)
        now = self._now_iso()
        expires = self._expires_iso() if self.ttl_seconds > 0 else None

        with self._lock:
            try:
                self._conn.execute(
                    "INSERT OR IGNORE INTO url_dedup "
                    "(normalized_url, original_url, first_seen_at, last_seen_at, expires_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (norm, url, now, now, expires),
                )
                inserted = self._conn.execute("SELECT changes()").fetchone()[0]
                if inserted:
                    self._conn.commit()
                    return True

                # Already exists — update
                self._conn.execute(
                    "UPDATE url_dedup SET last_seen_at = ?, hit_count = hit_count + 1, "
                    "expires_at = COALESCE(expires_at, ?) "
                    "WHERE normalized_url = ?",
                    (now, expires, norm),
                )
                self._conn.commit()
                return False
            except sqlite3.OperationalError as e:
                # If DB is broken, try to reinitialize
                self._init_db()
                return False

    # ── Content hash dedup ───────────────────────────────────────

    def is_duplicate_content(self, content: str, url: str = "") -> bool:
        """Check if content hash has already been seen."""
        h = self._hash_content(content)
        with self._lock:
            cur = self._conn.execute(
                "SELECT 1 FROM content_dedup WHERE content_hash = ? AND "
                "(expires_at IS NULL OR expires_at > ?)",
                (h, self._now_iso()),
            )
            return cur.fetchone() is not None

    def mark_content(self, content: str, url: str = "",
                     title: str = "") -> bool:
        """Mark content hash as seen. Returns True if new."""
        h = self._hash_content(content)
        now = self._now_iso()
        expires = self._expires_iso() if self.ttl_seconds > 0 else None

        with self._lock:
            try:
                self._conn.execute(
                    "INSERT OR IGNORE INTO content_dedup "
                    "(content_hash, url, title, first_seen_at, last_seen_at, expires_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (h, url, title[:500], now, now, expires),
                )
                inserted = self._conn.execute("SELECT changes()").fetchone()[0]
                if inserted:
                    self._conn.commit()
                    return True

                self._conn.execute(
                    "UPDATE content_dedup SET last_seen_at = ?, hit_count = hit_count + 1, "
                    "expires_at = COALESCE(expires_at, ?) "
                    "WHERE content_hash = ?",
                    (now, expires, h),
                )
                self._conn.commit()
                return False
            except sqlite3.OperationalError:
                self._init_db()
                return False

    # ── Cleanup ──────────────────────────────────────────────────

    def purge_expired(self) -> int:
        """Remove all expired entries. Returns count of removed rows."""
        now = self._now_iso()
        with self._lock:
            u = self._conn.execute(
                "DELETE FROM url_dedup WHERE expires_at IS NOT NULL AND expires_at <= ?",
                (now,),
            )
            c = self._conn.execute(
                "DELETE FROM content_dedup WHERE expires_at IS NOT NULL AND expires_at <= ?",
                (now,),
            )
            self._conn.commit()
            return u.rowcount + c.rowcount

    # ── Stats ────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        with self._lock:
            urls = self._conn.execute("SELECT COUNT(*) FROM url_dedup").fetchone()[0]
            contents = self._conn.execute("SELECT COUNT(*) FROM content_dedup").fetchone()[0]
            total_hits = self._conn.execute(
                "SELECT COALESCE(SUM(hit_count), 0) FROM url_dedup"
            ).fetchone()[0]
            return {
                "total_urls": urls,
                "total_contents": contents,
                "total_hits": total_hits,
                "db_path": self.db_path or ":memory:",
                "ttl_seconds": self.ttl_seconds,
            }

    def clear(self):
        """Remove all entries (for testing)."""
        with self._lock:
            self._conn.execute("DELETE FROM url_dedup")
            self._conn.execute("DELETE FROM content_dedup")
            self._conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Internals ────────────────────────────────────────────────

    @staticmethod
    def _normalize_url(url: str) -> str:
        from urllib.parse import urlparse, urlunparse
        try:
            p = urlparse(url)
            # Lowercase scheme+netloc, strip trailing slash
            norm = urlunparse((
                p.scheme.lower(),
                p.netloc.lower(),
                p.path.rstrip("/") or "/",
                "", "", ""
            ))
            return norm[:500]
        except Exception:
            return url[:500].lower().strip()

    @staticmethod
    def _hash_content(content: str) -> str:
        return hashlib.sha256((content or "").encode("utf-8")).hexdigest()

    @staticmethod
    def _now_iso() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%S")

    def _expires_iso(self) -> str:
        import datetime
        dt = datetime.datetime.now() + datetime.timedelta(seconds=self.ttl_seconds)
        return dt.strftime("%Y-%m-%dT%H:%M:%S")
