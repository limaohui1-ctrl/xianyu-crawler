"""
CLI Dashboard — unified text-based dashboard for ACS subsystems.

Displays:
  - Shadow comparison summary
  - AI cost report
  - Review queue status
  - Structure change history

Supports approve/reject/needs_more_data/archive review actions.

Usage:
    python -m acs.dashboard.cli_dashboard
    python -m acs.dashboard.cli_dashboard --site example_site
    python -m acs.dashboard.cli_dashboard --approve 42 --note "Looks good"
    python -m acs.dashboard.cli_dashboard --reject 43 --note "Bad match"
    python -m acs.dashboard.cli_dashboard --export markdown
    python -m acs.dashboard.cli_dashboard --export json
"""

import sys
import os
import json
import argparse
from typing import Optional

from acs.dashboard.report_builder import ReportBuilder
from acs.dashboard.review_queue_view import ReviewQueueView
from acs.dashboard.cost_view import CostView
from acs.dashboard.shadow_view import ShadowView
from acs.dashboard.structure_view import StructureView


class CLIDashboard:
    """Unified CLI dashboard for ACS monitoring and review.

    Does NOT auto-apply anything. All review actions are logged only.
    """

    def __init__(
        self,
        shadow_analyzer=None,
        cost_report=None,
        ai_parse_policy=None,
        review_store=None,
        structure_store=None,
    ):
        self.shadow_analyzer = shadow_analyzer
        self.cost_report = cost_report
        self.ai_parse_policy = ai_parse_policy
        self.review_store = review_store
        self.structure_store = structure_store

        # Views
        self.shadow_view = ShadowView(shadow_analyzer=shadow_analyzer)
        self.cost_view = CostView(cost_report=cost_report)
        if review_store:
            self.review_queue = ReviewQueueView(review_store)
        else:
            self.review_queue = None
        if structure_store:
            self.structure_view = StructureView(structure_store)
        else:
            self.structure_view = None

    def render(self, site_id: str = "") -> str:
        """Render full dashboard as text."""
        sections = []

        # Shadow
        sections.append(self.shadow_view.markdown())

        # Cost
        cost_data = {}
        if self.cost_report:
            cost_data = self.cost_report.get_summary().to_dict()
        elif self.ai_parse_policy:
            cost_data = self.ai_parse_policy.get_stats()
        sections.append(self.cost_view.markdown())
        sections.append("")

        # Review Queue
        if self.review_queue:
            sections.append(self.review_queue.markdown(site_id=site_id))

        # Structure
        if self.structure_view:
            sections.append(self.structure_view.markdown(site_id=site_id))

        # Safety footer
        sections.append("")
        sections.append("---")
        sections.append("> ⚠️ ACS_MODE=shadow remains default.")
        sections.append("> No selectors are auto-applied. No API keys in output.")
        sections.append("> All approved candidates are recommendations only.")

        return "\n\n".join(sections)

    def approve(self, review_id: int, note: str = "") -> dict:
        from acs.review.pending_review import PendingReviewManager
        if not self.review_store:
            return {"success": False, "error": "No review store configured"}
        mgr = PendingReviewManager(self.review_store)
        ok = mgr.approve(review_id, note)
        return {"success": ok, "action": "approve", "review_id": review_id}

    def reject(self, review_id: int, note: str = "") -> dict:
        from acs.review.pending_review import PendingReviewManager
        if not self.review_store:
            return {"success": False, "error": "No review store configured"}
        mgr = PendingReviewManager(self.review_store)
        ok = mgr.reject(review_id, note)
        return {"success": ok, "action": "reject", "review_id": review_id}

    def needs_more_data(self, review_id: int, note: str = "") -> dict:
        from acs.review.pending_review import PendingReviewManager
        if not self.review_store:
            return {"success": False, "error": "No review store configured"}
        mgr = PendingReviewManager(self.review_store)
        ok = mgr.request_more_data(review_id, note)
        return {"success": ok, "action": "needs_more_data", "review_id": review_id}

    def archive(self, review_id: int) -> dict:
        from acs.review.pending_review import PendingReviewManager
        if not self.review_store:
            return {"success": False, "error": "No review store configured"}
        mgr = PendingReviewManager(self.review_store)
        ok = mgr.archive(review_id)
        return {"success": ok, "action": "archive", "review_id": review_id}

    def export(self, fmt: str = "markdown", site_id: str = "") -> str:
        if fmt == "json":
            builder = ReportBuilder(
                shadow_analyzer=self.shadow_analyzer,
                cost_report=self.cost_report,
                ai_parse_policy=self.ai_parse_policy,
                review_store=self.review_store,
                structure_store=self.structure_store,
            )
            return json.dumps(builder.build_dict(), ensure_ascii=False, indent=2)
        return self.render(site_id=site_id)


def main():
    parser = argparse.ArgumentParser(description="ACS CLI Dashboard")
    parser.add_argument("--site", default="", help="Filter by site_id")
    parser.add_argument("--approve", type=int, default=0, help="Approve review ID")
    parser.add_argument("--reject", type=int, default=0, help="Reject review ID")
    parser.add_argument("--needs-more-data", type=int, default=0, help="Mark review as needs_more_data")
    parser.add_argument("--archive", type=int, default=0, help="Archive review ID")
    parser.add_argument("--note", default="", help="Reviewer note")
    parser.add_argument("--export", choices=["markdown", "json"], help="Export format")
    args = parser.parse_args()

    # Optional stores — loaded if DB files exist
    review_store = None
    structure_store = None
    try:
        from acs.storage.repair_review_store import RepairReviewStore
        if os.path.exists("acs_data/reviews.db"):
            review_store = RepairReviewStore("acs_data/reviews.db")
    except Exception:
        pass
    try:
        from acs.storage.structure_history_store import StructureHistoryStore
        if os.path.exists("acs_data/structure_history.db"):
            structure_store = StructureHistoryStore("acs_data/structure_history.db")
    except Exception:
        pass

    dash = CLIDashboard(review_store=review_store, structure_store=structure_store)

    # Actions
    if args.approve:
        result = dash.approve(args.approve, args.note)
        print(json.dumps(result, ensure_ascii=False))
    elif args.reject:
        result = dash.reject(args.reject, args.note)
        print(json.dumps(result, ensure_ascii=False))
    elif args.needs_more_data:
        result = dash.needs_more_data(args.needs_more_data, args.note)
        print(json.dumps(result, ensure_ascii=False))
    elif args.archive:
        result = dash.archive(args.archive)
        print(json.dumps(result, ensure_ascii=False))
    elif args.export:
        print(dash.export(fmt=args.export, site_id=args.site))
    else:
        print(dash.render(site_id=args.site))


if __name__ == "__main__":
    main()
