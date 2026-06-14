"""Cost view — displays AI cost statistics for the dashboard."""

from typing import Optional
from acs.observability.cost_report import CostReport


class CostView:
    """Dashboard view for AI cost statistics.

    Args:
        cost_report: CostReport instance
    """

    def __init__(self, cost_report: Optional[CostReport] = None):
        self.cost_report = cost_report or CostReport()

    def get_summary(self) -> dict:
        return self.cost_report.get_summary().to_dict()

    def markdown(self) -> str:
        return self.cost_report.markdown_summary()

    @staticmethod
    def from_audit_stats(stats: dict) -> str:
        """Quick Markdown from audit stats dict."""
        lines = [
            "## Cost Summary",
            "",
            "| Metric | Value |",
            "| ------ | ----- |",
            f"| Total calls | {stats.get('total_calls', 0)} |",
            f"| Successful | {stats.get('successful_calls', 0)} |",
            f"| Failed | {stats.get('failed_calls', 0)} |",
            f"| Total tokens | {stats.get('total_tokens', 0):,} |",
            f"| Estimated cost | ${stats.get('estimated_cost', 0)} |",
        ]
        return "\n".join(lines)
