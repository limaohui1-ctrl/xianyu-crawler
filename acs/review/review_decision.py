"""
Review decision — structured decision records for each review action.

Every review action (approve/reject/request_more_data/archive) produces
a ReviewDecision record with full audit trail.

Usage:
    from acs.review.review_decision import ReviewDecision

    d = ReviewDecision(review_id=42, action="approved", reviewer="admin")
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum
import time


class ReviewAction(str, Enum):
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_MORE_DATA = "needs_more_data"
    ARCHIVED = "archived"
    AUTO_APPROVED_HIGH_CONF = "auto_approved_high_conf"


@dataclass
class ReviewDecision:
    """A single review decision with full audit trail.

    NOTE: Even "approved" or "auto_approved_high_conf" decisions
    do NOT apply selectors to production.  They are recommendations only.
    """

    review_id: int = 0
    action: str = "submitted"
    reviewer: str = "system"
    note: str = ""
    created_at: str = ""
    site_id: str = ""
    field_name: str = ""
    old_selector: str = ""
    candidate_selector: str = ""
    confidence: float = 0.0
    auto_applied: bool = False  # Phase 5: ALWAYS False

    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    def to_dict(self) -> dict:
        return {
            "review_id": self.review_id,
            "action": self.action,
            "reviewer": self.reviewer,
            "note": self.note,
            "created_at": self.created_at,
            "site_id": self.site_id,
            "field": self.field_name,
            "old_selector": self.old_selector,
            "candidate_selector": self.candidate_selector,
            "confidence": self.confidence,
            "auto_applied": self.auto_applied,
        }

    @classmethod
    def from_review_item(cls, item, action: str,
                         reviewer: str = "system",
                         note: str = "") -> "ReviewDecision":
        """Create a decision from a ReviewItem."""
        return cls(
            review_id=item.review_id,
            action=action,
            reviewer=reviewer,
            note=note,
            site_id=item.site_id,
            field_name=item.field_name,
            old_selector=item.old_selector,
            candidate_selector=item.candidate_selector,
            confidence=item.confidence,
        )


@dataclass
class DecisionLog:
    """Accumulated review decisions for a session."""

    decisions: List[ReviewDecision] = field(default_factory=list)

    def record(self, decision: ReviewDecision):
        self.decisions.append(decision)

    def to_list(self) -> List[dict]:
        return [d.to_dict() for d in self.decisions]

    def get_stats(self) -> dict:
        actions = {}
        for d in self.decisions:
            actions[d.action] = actions.get(d.action, 0) + 1
        return {
            "total_decisions": len(self.decisions),
            "by_action": actions,
            "auto_applied_count": sum(1 for d in self.decisions if d.auto_applied),
        }
