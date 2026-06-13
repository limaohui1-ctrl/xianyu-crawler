"""Shadow view — displays ACS shadow comparison data for the dashboard."""

from typing import Optional, Any


class ShadowView:
    """Dashboard view for ACS shadow comparison data.

    Args:
        shadow_analyzer: ShadowAnalyzer instance (optional)
        shadow_stats: Pre-computed shadow stats dict (optional)
    """

    def __init__(self, shadow_analyzer=None, shadow_stats: dict = None):
        self.shadow_analyzer = shadow_analyzer
        self.shadow_stats = shadow_stats or {}

    def get_summary(self) -> dict:
        if self.shadow_analyzer and hasattr(self.shadow_analyzer, 'analyze'):
            try:
                r = self.shadow_analyzer.analyze()
                return r.to_dict() if hasattr(r, 'to_dict') else {}
            except Exception:
                pass
        return self.shadow_stats

    def markdown(self) -> str:
        s = self.get_summary()
        if not s:
            return "## Shadow — No data"

        lines = [
            "## Shadow Comparison",
            "",
            "| Metric | Value |",
            "| ------ | ----- |",
            f"| Total entries | {s.get('total_entries', 0)} |",
            f"| ACS success rate | {s.get('acs_success_rate', 0):.1%} |",
            f"| ACS avg completeness | {s.get('acs_avg_completeness', 0):.1f}% |",
            f"| ACS better than legacy | {s.get('acs_superior_count', 0)} |",
            f"| ACS worse than legacy | {s.get('acs_inferior_count', 0)} |",
            f"| Comparable | {s.get('acs_comparable_count', 0)} |",
            f"| Ready for on mode | {s.get('ready_for_on_mode', False)} |",
            "",
        ]
        pdict = s.get('parser_distribution', {})
        if pdict:
            lines.append("### Parser Distribution")
            for k, v in sorted(pdict.items(), key=lambda x: -x[1])[:5]:
                lines.append(f"- {k}: {v}")

        return "\n".join(lines)
