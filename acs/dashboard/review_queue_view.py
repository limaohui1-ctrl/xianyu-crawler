"""Review queue view — displays pending_review candidates with status breakdown."""

from typing import Dict, List, Optional
from acs.storage.repair_review_store import RepairReviewStore


class ReviewQueueView:
    """Read-only view of the repair review queue.

    Args:
        store: RepairReviewStore instance
    """

    def __init__(self, store: RepairReviewStore):
        self.store = store

    def get_summary(self) -> dict:
        stats = self.store.get_stats()
        by_status = stats.get("by_status", {})
        return {
            "total": stats.get("total", 0),
            "pending_review": by_status.get("pending_review", 0),
            "approved": by_status.get("approved", 0),
            "rejected": by_status.get("rejected", 0),
            "needs_more_data": by_status.get("needs_more_data", 0),
            "archived": by_status.get("archived", 0),
        }

    def get_pending(self, site_id: str = "", limit: int = 100) -> List[dict]:
        return self.store.get_pending(site_id=site_id, limit=limit)

    def get_approved(self, site_id: str = "", limit: int = 50) -> List[dict]:
        return self.store.get_approved(site_id=site_id, limit=limit)

    def markdown(self, site_id: str = "") -> str:
        summary = self.get_summary()
        pending = self.get_pending(site_id=site_id, limit=20)
        approved = self.get_approved(site_id=site_id, limit=10)

        lines = [
            "## Review Queue",
            "",
            "| Status | Count |",
            "| ------ | ----- |",
            f"| Pending | {summary['pending_review']} |",
            f"| Approved | {summary['approved']} |",
            f"| Rejected | {summary['rejected']} |",
            f"| Needs more data | {summary['needs_more_data']} |",
            f"| Archived | {summary['archived']} |",
            "",
        ]

        if pending:
            lines.append("### Pending Review")
            for item in pending[:10]:
                lines.append(
                    f"- #{item['id']} `{item['field_name']}`: "
                    f"`{item['old_selector']}` → `{item['candidate_selector']}` "
                    f"(conf={item.get('confidence', 0):.2f})"
                )

        if approved:
            lines.append("")
            lines.append("### Approved (NOT auto-applied)")
            for item in approved[:5]:
                lines.append(
                    f"- #{item['id']} `{item['field_name']}`: "
                    f"`{item['candidate_selector']}` — {item.get('reviewer_note', '')[:50]}"
                )

        return "\n".join(lines)
