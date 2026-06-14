"""
Pending review — manages the human review workflow for selector repair candidates.

Enforces the golden rule: nothing is auto-applied.
All candidates go through pending_review → approved/rejected/needs_more_data.

Usage:
    from acs.review.pending_review import PendingReviewManager

    mgr = PendingReviewManager(store)
    mgr.submit(site_id=..., field="title", ...)
    mgr.approve(review_id=42, note="Selector works on test pages")
    # Even approved, the candidate is NOT applied automatically.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import time

from acs.storage.repair_review_store import RepairReviewStore, REVIEW_STATUSES


@dataclass
class ReviewItem:
    """A single review item."""
    review_id: int = 0
    site_id: str = ""
    url: str = ""
    field_name: str = ""
    old_selector: str = ""
    candidate_selector: str = ""
    confidence: float = 0.0
    evidence: str = ""
    review_status: str = "pending_review"
    reviewed_at: str = ""
    reviewer_note: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "review_id": self.review_id,
            "site_id": self.site_id,
            "url": self.url,
            "field": self.field_name,
            "old_selector": self.old_selector,
            "candidate_selector": self.candidate_selector,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "status": self.review_status,
            "reviewed_at": self.reviewed_at,
            "reviewer_note": self.reviewer_note,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: dict) -> "ReviewItem":
        return cls(
            review_id=row.get("id", 0),
            site_id=row.get("site_id", ""),
            url=row.get("url", ""),
            field_name=row.get("field_name", ""),
            old_selector=row.get("old_selector", ""),
            candidate_selector=row.get("candidate_selector", ""),
            confidence=row.get("confidence", 0.0),
            evidence=row.get("evidence", ""),
            review_status=row.get("review_status", "pending_review"),
            reviewed_at=row.get("reviewed_at", ""),
            reviewer_note=row.get("reviewer_note", ""),
            created_at=row.get("created_at", ""),
        )


class PendingReviewManager:
    """Orchestrates the human review pipeline.

    SECURITY: All state mutations go through explicit method calls.
    No automatic state transitions.  Approved items are logged but
    NOT applied to production selectors.

    Args:
        store: RepairReviewStore instance
    """

    def __init__(self, store: Optional[RepairReviewStore] = None):
        self.store = store or RepairReviewStore()
        self._audit_log: List[dict] = []

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
        """Submit a candidate for human review. Returns review_id."""
        rid = self.store.submit(
            site_id=site_id,
            url=url,
            field_name=field_name,
            old_selector=old_selector,
            candidate_selector=candidate_selector,
            confidence=confidence,
            evidence=evidence,
            ai_hint=ai_hint,
            match_count=match_count,
        )
        self._audit({"action": "submit", "review_id": rid, "field": field_name})
        return rid

    def submit_from_repair_result(self, result, url: str = "",
                                  site_id: str = "") -> List[int]:
        """Submit all candidates from a FieldRepairResult."""
        ids = []
        if hasattr(result, 'candidate_selectors'):
            for c in result.candidate_selectors:
                rid = self.submit(
                    site_id=site_id or getattr(result, 'site_id', ''),
                    url=url or getattr(result, 'url', ''),
                    field_name=getattr(result, 'field', ''),
                    old_selector=getattr(result, 'old_selector', ''),
                    candidate_selector=getattr(c, 'selector', str(c)),
                    confidence=getattr(c, 'confidence', 0.0),
                    evidence=getattr(c, 'evidence', ''),
                )
                ids.append(rid)
        return ids

    # ── Review actions ───────────────────────────────────────────

    def approve(self, review_id: int, note: str = "") -> bool:
        """Approve a candidate (still does NOT apply to production)."""
        if not self._can_transition(review_id, "approved"):
            return False
        ok = self.store.update_review(review_id, "approved", note)
        if ok:
            self._audit({"action": "approve", "review_id": review_id, "note": note})
        return ok

    def reject(self, review_id: int, note: str = "") -> bool:
        if not self._can_transition(review_id, "rejected"):
            return False
        ok = self.store.update_review(review_id, "rejected", note)
        if ok:
            self._audit({"action": "reject", "review_id": review_id, "note": note})
        return ok

    def request_more_data(self, review_id: int, note: str = "") -> bool:
        if not self._can_transition(review_id, "needs_more_data"):
            return False
        ok = self.store.update_review(review_id, "needs_more_data", note)
        if ok:
            self._audit({"action": "request_more_data", "review_id": review_id})
        return ok

    def archive(self, review_id: int) -> bool:
        ok = self.store.update_review(review_id, "archived")
        if ok:
            self._audit({"action": "archive", "review_id": review_id})
        return ok

    # ── Query ────────────────────────────────────────────────────

    def get_pending(self, site_id: str = "", field_name: str = "",
                    limit: int = 50) -> List[ReviewItem]:
        rows = self.store.get_pending(site_id, field_name, limit)
        return [ReviewItem.from_row(r) for r in rows]

    def get_approved(self, site_id: str = "", limit: int = 50) -> List[ReviewItem]:
        rows = self.store.get_approved(site_id, limit)
        return [ReviewItem.from_row(r) for r in rows]

    def get_by_id(self, review_id: int) -> Optional[ReviewItem]:
        row = self.store.get_by_id(review_id)
        return ReviewItem.from_row(row) if row else None

    # ── Bulk ─────────────────────────────────────────────────────

    def approve_above_confidence(self, site_id: str, threshold: float = 0.9,
                                 note: str = "") -> int:
        """Batch-approve high-confidence candidates (still no auto-apply)."""
        pending = self.store.get_pending(site_id=site_id)
        count = 0
        for p in pending:
            if p.get("confidence", 0) >= threshold:
                if self.approve(p["id"], note):
                    count += 1
        return count

    # ── Audit ────────────────────────────────────────────────────

    @property
    def audit_log(self) -> List[dict]:
        return list(self._audit_log)

    def _audit(self, entry: dict):
        entry["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._audit_log.append(entry)
        if len(self._audit_log) > 1000:
            self._audit_log = self._audit_log[-500:]

    def _can_transition(self, review_id: int, target: str) -> bool:
        """Verify the review exists and target status is valid."""
        if target not in REVIEW_STATUSES:
            return False
        item = self.get_by_id(review_id)
        if item is None:
            return False
        if item.review_status == "archived" and target != "archived":
            return False
        return True

    def get_stats(self) -> dict:
        db_stats = self.store.get_stats()
        db_stats["audit_entries"] = len(self._audit_log)
        return db_stats
