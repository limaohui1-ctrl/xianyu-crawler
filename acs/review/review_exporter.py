"""
Review exporter — exports review decisions and repair candidates to various formats.

Supports:
  - JSON export (for dashboard / API consumption)
  - CSV export (for spreadsheet review)
  - Markdown summary

Usage:
    from acs.review.review_exporter import ReviewExporter

    exporter = ReviewExporter(manager)
    json_str = exporter.export_json()
"""

import json
import time
from typing import List, Optional

from acs.review.pending_review import PendingReviewManager, ReviewItem


class ReviewExporter:
    """Export review data from PendingReviewManager.

    Args:
        manager: PendingReviewManager instance
    """

    def __init__(self, manager: PendingReviewManager):
        self.manager = manager

    # ── JSON export ──────────────────────────────────────────────

    def export_json(self, site_id: str = "", status_filter: Optional[str] = None,
                    limit: int = 200) -> str:
        """Export reviews as JSON string."""
        if status_filter:
            rows = self.manager.store.get_by_status(status_filter, limit)
        else:
            rows = self.manager.store.get_pending(site_id=site_id, limit=limit)

        items = [ReviewItem.from_row(r).to_dict() for r in rows]
        stats = self.manager.get_stats()

        result = {
            "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "stats": stats,
            "reviews": items,
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    # ── CSV export ───────────────────────────────────────────────

    def export_csv(self, site_id: str = "", status_filter: str = "pending_review",
                   limit: int = 200) -> str:
        """Export reviews as CSV string."""
        if status_filter:
            rows = self.manager.store.get_by_status(status_filter, limit)
        else:
            rows = self.manager.store.get_pending(site_id=site_id, limit=limit)

        if not rows:
            return "id,site_id,field,old_selector,candidate_selector,confidence,status\n"

        import io
        import csv
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "id", "site_id", "field", "old_selector", "candidate_selector",
            "confidence", "status", "evidence",
        ])
        for r in rows:
            item = ReviewItem.from_row(r)
            writer.writerow([
                item.review_id, item.site_id, item.field_name,
                item.old_selector, item.candidate_selector,
                item.confidence, item.review_status,
                item.evidence[:200] if item.evidence else "",
            ])
        return output.getvalue()

    # ── Markdown summary ─────────────────────────────────────────

    def export_markdown(self, site_id: str = "") -> str:
        """Generate a Markdown summary of all review items."""
        stats = self.manager.get_stats()
        by_status = stats.get("by_status", {})
        pending = self.manager.get_pending(site_id=site_id, limit=50)
        approved = self.manager.get_approved(site_id=site_id, limit=20)

        lines = [
            "# Repair Review Summary",
            "",
            f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Statistics",
            f"- Total reviews: {stats.get('total', 0)}",
            f"- Pending: {by_status.get('pending_review', 0)}",
            f"- Approved: {by_status.get('approved', 0)}",
            f"- Rejected: {by_status.get('rejected', 0)}",
            f"- Needs more data: {by_status.get('needs_more_data', 0)}",
            "",
        ]

        if pending:
            lines.append("## Pending Review")
            lines.append("")
            lines.append("| ID | Site | Field | Old → New | Confidence |")
            lines.append("| -- | ---- | ----- | --------- | ---------- |")
            for item in pending[:20]:
                lines.append(
                    f"| {item.review_id} | {item.site_id[:20]} | {item.field_name} | "
                    f"{item.old_selector[:20]} → {item.candidate_selector[:20]} | "
                    f"{item.confidence:.2f} |"
                )
            lines.append("")

        if approved:
            lines.append("## Approved (NOT auto-applied)")
            lines.append("")
            lines.append("| ID | Site | Field | Old → New | Note |")
            lines.append("| -- | ---- | ----- | --------- | ---- |")
            for item in approved[:20]:
                lines.append(
                    f"| {item.review_id} | {item.site_id[:20]} | {item.field_name} | "
                    f"{item.old_selector[:20]} → {item.candidate_selector[:20]} | "
                    f"{item.reviewer_note[:30]} |"
                )
            lines.append("")

        lines.append("> ⚠️ All approved candidates remain recommendations only.")
        lines.append("> Auto-application to production is NOT implemented.")

        return "\n".join(lines)
