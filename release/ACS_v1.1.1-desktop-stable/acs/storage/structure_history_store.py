"""
Structure history store — persists DOM/selector/parser history for before/after comparison.

Stores structure snapshots (not full HTML) keyed by site_id + url:
  - DOM node count
  - Selector match counts per field
  - Change scores over time
  - Parser distribution
  - JSON-LD hashes

Used by StructureDiffer to compare current page against historical baselines.

Usage:
    from acs.storage.structure_history_store import StructureHistoryStore

    store = StructureHistoryStore("acs_data/structure_history.db")
    store.save_snapshot(site_id="example", url="...", snapshot={...})
    recent = store.get_recent("example", limit=10)
"""

import json
import os
import sqlite3
import threading
import time
import hashlib
from typing import Any, Dict, List, Optional


class StructureHistoryStore:
    """Persistent storage for page structure snapshots.

    Args:
        db_path: SQLite database path
    """

    def __init__(self, db_path: str = "acs_data/structure_history.db"):
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
                CREATE TABLE IF NOT EXISTS structure_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    dom_node_count INTEGER,
                    change_score REAL DEFAULT 0.0,
                    selector_states TEXT,
                    jsonld_hash TEXT,
                    parser_used TEXT,
                    field_extraction_rates TEXT,
                    body_hash TEXT
                )
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_struct_site_url
                ON structure_snapshots(site_id, url)
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_struct_captured
                ON structure_snapshots(captured_at)
            """)
            self._conn.commit()

    # ── Save snapshot ────────────────────────────────────────────

    def save_snapshot(
        self,
        site_id: str,
        url: str,
        dom_node_count: int = 0,
        change_score: float = 0.0,
        selector_states: Optional[Dict[str, List[Dict]]] = None,
        jsonld_hash: str = "",
        parser_used: str = "",
        field_extraction_rates: Optional[Dict[str, float]] = None,
        body_text: str = "",
    ) -> int:
        """Save a structure snapshot. Returns row id."""
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        body_hash = hashlib.md5((body_text or "").encode()).hexdigest() if body_text else ""

        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO structure_snapshots
                   (site_id, url, captured_at, dom_node_count, change_score,
                    selector_states, jsonld_hash, parser_used,
                    field_extraction_rates, body_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    site_id, url[:500], now, dom_node_count, change_score,
                    json.dumps(selector_states, ensure_ascii=False) if selector_states else "{}",
                    jsonld_hash, parser_used,
                    json.dumps(field_extraction_rates, ensure_ascii=False) if field_extraction_rates else "{}",
                    body_hash,
                ),
            )
            self._conn.commit()
            return cur.lastrowid

    # ── Query ────────────────────────────────────────────────────

    def get_recent(self, site_id: str, limit: int = 10) -> List[dict]:
        """Get the most recent snapshots for a site."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM structure_snapshots WHERE site_id = ? "
                "ORDER BY captured_at DESC LIMIT ?",
                (site_id, limit),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_latest(self, site_id: str, url: str = "") -> Optional[dict]:
        """Get the most recent snapshot for a site+url combination."""
        with self._lock:
            if url:
                row = self._conn.execute(
                    "SELECT * FROM structure_snapshots WHERE site_id = ? AND url = ? "
                    "ORDER BY captured_at DESC LIMIT 1",
                    (site_id, url),
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT * FROM structure_snapshots WHERE site_id = ? "
                    "ORDER BY captured_at DESC LIMIT 1",
                    (site_id,),
                ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_by_url(self, url: str, limit: int = 5) -> List[dict]:
        """Get recent snapshots for a specific URL."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM structure_snapshots WHERE url = ? "
                "ORDER BY captured_at DESC LIMIT ?",
                (url[:500], limit),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_site_stats(self, site_id: str) -> dict:
        """Get aggregate stats for a site."""
        with self._lock:
            count = self._conn.execute(
                "SELECT COUNT(*) FROM structure_snapshots WHERE site_id = ?",
                (site_id,),
            ).fetchone()[0]
            avg_change = self._conn.execute(
                "SELECT AVG(change_score) FROM structure_snapshots WHERE site_id = ?",
                (site_id,),
            ).fetchone()[0] or 0.0
            return {
                "site_id": site_id,
                "total_snapshots": count,
                "avg_change_score": round(avg_change, 4),
            }

    # ── Bulk import ──────────────────────────────────────────────

    def save_batch(self, snapshots: List[dict]) -> int:
        """Save multiple snapshots in a transaction. Returns count saved."""
        count = 0
        with self._lock:
            for snap in snapshots:
                try:
                    self._conn.execute(
                        """INSERT INTO structure_snapshots
                           (site_id, url, captured_at, dom_node_count, change_score,
                            selector_states, jsonld_hash, parser_used,
                            field_extraction_rates, body_hash)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            snap.get("site_id", ""),
                            snap.get("url", "")[:500],
                            snap.get("captured_at", self._now_iso()),
                            snap.get("dom_node_count", 0),
                            snap.get("change_score", 0.0),
                            json.dumps(snap.get("selector_states", {}), ensure_ascii=False),
                            snap.get("jsonld_hash", ""),
                            snap.get("parser_used", ""),
                            json.dumps(snap.get("field_extraction_rates", {}), ensure_ascii=False),
                            snap.get("body_hash", ""),
                        ),
                    )
                    count += 1
                except Exception:
                    pass
            self._conn.commit()
        return count

    # ── Maintenance ──────────────────────────────────────────────

    def clean_old(self, max_age_days: int = 90) -> int:
        """Remove snapshots older than max_age_days. Returns rows deleted."""
        import datetime
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=max_age_days))
        cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%S")
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM structure_snapshots WHERE captured_at < ?",
                (cutoff_str,),
            )
            self._conn.commit()
            return cur.rowcount

    def get_stats(self) -> dict:
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) FROM structure_snapshots").fetchone()[0]
            sites = self._conn.execute(
                "SELECT COUNT(DISTINCT site_id) FROM structure_snapshots"
            ).fetchone()[0]
            return {"total_snapshots": total, "unique_sites": sites, "db_path": self.db_path}

    def clear(self):
        with self._lock:
            self._conn.execute("DELETE FROM structure_snapshots")
            self._conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()

    # ── Internals ────────────────────────────────────────────────

    @staticmethod
    def _row_to_dict(row) -> dict:
        cols = ["id", "site_id", "url", "captured_at", "dom_node_count",
                "change_score", "selector_states", "jsonld_hash",
                "parser_used", "field_extraction_rates", "body_hash"]
        d = dict(zip(cols, row))
        # Deserialize JSON columns
        for col in ("selector_states", "field_extraction_rates"):
            try:
                d[col] = json.loads(d.get(col, "{}"))
            except (json.JSONDecodeError, TypeError):
                d[col] = {}
        return d

    @staticmethod
    def _now_iso() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%S")
