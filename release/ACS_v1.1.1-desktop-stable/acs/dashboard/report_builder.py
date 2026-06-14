"""
Dashboard report builder — aggregates data from all ACS subsystems.

Pulls from:
  - ShadowAnalyzer (shadow comparison data)
  - CostReport / CostController (cost data)
  - AIParsePolicy (AI call stats)
  - RepairReviewStore (review queue)
  - StructureHistoryStore (structure changes)

Generates a unified Markdown/JSON report.  NEVER includes API keys.

Usage:
    from acs.dashboard.report_builder import ReportBuilder
    builder = ReportBuilder(...)
    report = builder.build()
    print(report.markdown())
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import time


@dataclass
class DashboardReport:
    """Unified ACS dashboard report."""
    generated_at: str = ""
    shadow: Dict[str, Any] = field(default_factory=dict)
    cost: Dict[str, Any] = field(default_factory=dict)
    ai_parser: Dict[str, Any] = field(default_factory=dict)
    reviews: Dict[str, Any] = field(default_factory=dict)
    structure: Dict[str, Any] = field(default_factory=dict)
    safety: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "shadow": self.shadow,
            "cost": self.cost,
            "ai_parser": self.ai_parser,
            "reviews": self.reviews,
            "structure": self.structure,
            "safety": self.safety,
        }

    def markdown(self) -> str:
        lines = [
            "# ACS Dashboard Report",
            f"Generated: {self.generated_at}",
            "",
            "## Shadow Comparison",
        ]
        s = self.shadow
        lines.append(f"- Total entries: {s.get('total_entries', 0)}")
        lines.append(f"- ACS success rate: {s.get('acs_success_rate', 0):.1%}")
        lines.append(f"- ACS avg completeness: {s.get('acs_avg_completeness', 0):.1f}%")
        lines.append(f"- Ready for on mode: {s.get('ready_for_on_mode', False)}")
        lines.append("")
        lines.append("## Cost Report")
        c = self.cost
        lines.append(f"- Total AI calls: {c.get('total_ai_calls', 0)}")
        lines.append(f"- Total tokens: {c.get('total_tokens', 0):,}")
        lines.append(f"- Estimated cost: ${c.get('estimated_cost', 0)}")
        lines.append(f"- Cost limit reached: {c.get('cost_limit_reached', False)}")
        lines.append("")
        lines.append("## AI Parser")
        a = self.ai_parser
        lines.append(f"- Calls: {a.get('total_ai_calls', 0)}")
        lines.append(f"- Enabled: {a.get('ai_fallback_enabled', False)}")
        lines.append("")
        lines.append("## Review Queue")
        r = self.reviews
        lines.append(f"- Total: {r.get('total', 0)}")
        lines.append(f"- Pending: {r.get('pending', 0)}")
        lines.append(f"- Approved: {r.get('approved', 0)}")
        lines.append(f"- Rejected: {r.get('rejected', 0)}")
        lines.append("")
        lines.append("## Structure Changes")
        st = self.structure
        lines.append(f"- Total snapshots: {st.get('total_snapshots', 0)}")
        lines.append(f"- Unique sites: {st.get('unique_sites', 0)}")
        lines.append("")
        lines.append("## Safety")
        sf = self.safety
        lines.append(f"- ACS_MODE: {sf.get('acs_mode', 'shadow')}")
        lines.append(f"- Auto-apply enabled: {sf.get('auto_apply', False)}")
        return "\n".join(lines)


class ReportBuilder:
    """Builds unified dashboard reports from ACS subsystem data.

    All data sources are optional — the report gracefully handles
    missing data by showing zero/default values.
    """

    def __init__(
        self,
        shadow_analyzer=None,
        cost_report=None,
        ai_parse_policy=None,
        review_store=None,
        structure_store=None,
    ):
        self.shadow_analyzer = shadow_analyzer     # ShadowAnalyzer
        self.cost_report = cost_report             # CostReport
        self.ai_parse_policy = ai_parse_policy     # AIParsePolicy
        self.review_store = review_store           # RepairReviewStore
        self.structure_store = structure_store     # StructureHistoryStore

    def build(self) -> DashboardReport:
        report = DashboardReport(
            generated_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        # Shadow
        report.shadow = self._get_shadow_data()
        # Cost
        report.cost = self._get_cost_data()
        # AI parser
        report.ai_parser = self._get_ai_data()
        # Reviews
        report.reviews = self._get_review_data()
        # Structure
        report.structure = self._get_structure_data()
        # Safety
        report.safety = self._get_safety_data()
        return report

    def build_markdown(self) -> str:
        return self.build().markdown()

    def build_dict(self) -> dict:
        return self.build().to_dict()

    # ── Data extractors ──────────────────────────────────────────

    def _get_shadow_data(self) -> dict:
        if self.shadow_analyzer and hasattr(self.shadow_analyzer, 'analyze'):
            try:
                r = self.shadow_analyzer.analyze()
                return r.to_dict() if hasattr(r, 'to_dict') else {}
            except Exception:
                pass
        return {}

    def _get_cost_data(self) -> dict:
        if self.cost_report:
            try:
                s = self.cost_report.get_summary()
                return s.to_dict() if hasattr(s, 'to_dict') else vars(s)
            except Exception:
                pass
        return {}

    def _get_ai_data(self) -> dict:
        if self.ai_parse_policy:
            try:
                return self.ai_parse_policy.get_stats()
            except Exception:
                pass
        return {}

    def _get_review_data(self) -> dict:
        if self.review_store:
            try:
                s = self.review_store.get_stats()
                by = s.get("by_status", {})
                return {
                    "total": s.get("total", 0),
                    "pending": by.get("pending_review", 0),
                    "approved": by.get("approved", 0),
                    "rejected": by.get("rejected", 0),
                    "needs_more_data": by.get("needs_more_data", 0),
                }
            except Exception:
                pass
        return {}

    def _get_structure_data(self) -> dict:
        if self.structure_store:
            try:
                return self.structure_store.get_stats()
            except Exception:
                pass
        return {}

    def _get_safety_data(self) -> dict:
        import os
        return {
            "acs_mode": os.getenv("ACS_MODE", "shadow"),
            "auto_apply": False,  # Phase 6: always False
        }
