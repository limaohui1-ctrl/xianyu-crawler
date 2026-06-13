"""
Repair review store — persists pending_review selector candidates with review workflow.

Supports review states: pending_review, approved, rejected, needs_more_data, archived.

CRITICAL RULE: Even "approved" candidates do NOT auto-apply.  They remain
as recommendations only.  Auto-application is a future Phase concern.

Usage:
    from acs.storage.repair_review_store import RepairReviewStore

    store = RepairReviewStore("acs_data/reviews.db")
    store.submit(candidate)
    store.update_review(review_id, status="approved", note="Looks good")
"""

import json
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional


REVIEW_STATUSES = frozenset([
    "pending_review", "approved", "rejected", "needs_more_data", "archived",
])


class RepairReviewStore:
    """Persistent storage for selector repair review candidates.

    Args:
        db_path: SQLite database path
    """

    def __init__(self, db_path: str = "acs_data/reviews.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        with self._lock:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS repair_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    field_name TEXT NOT NULL,
                    old_selector TEXT NOT NULL,
                    candidate_selector TEXT NOT NULL,
                    confidence REAL DEFAULT 0.0,
                    evidence TEXT,
                    created_at TEXT NOT NULL,
                    review_status TEXT DEFAULT 'pending_review',
                    reviewed_at TEXT,
                    reviewer_note TEXT,
                    ai_hint TEXT,
                    match_count INTEGER DEFAULT 0
                )
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_review_status
                ON repair_reviews(review_status)
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_review_site_field
                ON repair_reviews(site_id, field_name)
            """)
            self._conn.commit()

    # ── Submit ───────────────────────────────────────────────────

    def submit(
        self,
        site_id: str,
        url: str,
        field_name: str,
        old_selector: str,
        candidate_selector: str,
        confidence: float = 0.0,
        evidence: str = "",
        ai_hint: str = "",
        match_count: int = 0,
    ) -> int:
        """Submit a selector repair candidate for review. Returns review id."""
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO repair_reviews
                   (site_id, url, field_name, old_selector, candidate_selector,
                    confidence, evidence, created_at, review_status, ai_hint, match_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending_review', ?, ?)""",
                (site_id, url[:500], field_name, old_selector, candidate_selector,
                 confidence, evidence[:1000], now, ai_hint[:500], match_count),
            )
            self._conn.commit()
            return cur.lastrowid

    def submit_batch(self, candidates: List[dict]) -> int:
        """Submit multiple candidates. Returns count accepted."""
        count = 0
        for c in candidates:
            try:
                self.submit(**c)
                count += 1
            except Exception:
                pass
        return count

    # ── Review ───────────────────────────────────────────────────

    def update_review(
        self,
        review_id: int,
        status: str,
        note: str = "",
    ) -> bool:
        """Update review status. Only valid statuses accepted.

        Args:
            review_id: Review row id
            status: One of: pending_review, approved, rejected, needs_more_data, archived
            note: Reviewer note

        Returns:
            True if updated, False if status invalid or id not found
        """
        if status not in REVIEW_STATUSES:
            return False

        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        with self._lock:
            cur = self._conn.execute(
                """UPDATE repair_reviews
                   SET review_status = ?, reviewed_at = ?, reviewer_note = ?
                   WHERE id = ?""",
                (status, now, note[:2000], review_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    # ── Query ────────────────────────────────────────────────────

    def get_pending(self, site_id: str = "", field_name: str = "",
                    limit: int = 50) -> List[dict]:
        """Get pending review candidates."""
        query = "SELECT * FROM repair_reviews WHERE review_status = 'pending_review'"
        params = []
        if site_id:
            query += " AND site_id = ?"
            params.append(site_id)
        if field_name:
            query += " AND field_name = ?"
            params.append(field_name)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_by_status(self, status: str, limit: int = 50) -> List[dict]:
        if status not in REVIEW_STATUSES:
            return []
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM repair_reviews WHERE review_status = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_approved(self, site_id: str = "", limit: int = 50) -> List[dict]:
        """Get approved candidates (still do NOT auto-apply)."""
        query = "SELECT * FROM repair_reviews WHERE review_status = 'approved'"
        params = []
        if site_id:
            query += " AND site_id = ?"
            params.append(site_id)
        query += " ORDER BY reviewed_at DESC LIMIT ?"
        params.append(limit)

        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_by_id(self, review_id: int) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM repair_reviews WHERE id = ?", (review_id,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    # ── Stats ────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) FROM repair_reviews").fetchone()[0]
            statuses = {}
            for s in REVIEW_STATUSES:
                c = self._conn.execute(
                    "SELECT COUNT(*) FROM repair_reviews WHERE review_status = ?", (s,)
                ).fetchone()[0]
                statuses[s] = c
            return {
                "total": total,
                "by_status": statuses,
                "db_path": self.db_path,
            }

    # ── Maintenance ──────────────────────────────────────────────

    def clear(self):
        with self._lock:
            self._conn.execute("DELETE FROM repair_reviews")
            self._conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()

    # ── Internals ────────────────────────────────────────────────

    @staticmethod
    def _row_to_dict(row) -> dict:
        cols = ["id", "site_id", "url", "field_name", "old_selector",
                "candidate_selector", "confidence", "evidence", "created_at",
                "review_status", "reviewed_at", "reviewer_note", "ai_hint",
                "match_count"]
        return dict(zip(cols, row))
