"""
Shadow analyzer — reads ACS shadow JSONL logs and produces comparison analytics.

This is a passive analysis tool; it does NOT modify any crawl behavior.
It reads existing shadow logs and provides data for strategy decisions.

Usage:
    from acs.observability.shadow_analyzer import ShadowAnalyzer

    sa = ShadowAnalyzer("acs_shadow_logs/data/acs_shadow.jsonl")
    report = sa.analyze()
    print(report.summary_text())

Requirements:
    - Input: path to acs_shadow.jsonl (produced by acs_shadow_collect)
    - Output: structured report with success rate, quality comparison, recommendations
    - Does NOT auto-switch ACS_MODE
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import json
import os


@dataclass
class ShadowReport:
    """Analysis report from shadow log data."""

    total_entries: int = 0
    acs_success_count: int = 0
    acs_failure_count: int = 0
    acs_success_rate: float = 0.0                    # 0.0 – 1.0
    acs_avg_completeness: float = 0.0
    acs_avg_body_len: float = 0.0
    legacy_avg_body_len: float = 0.0
    parser_distribution: Dict[str, int] = field(default_factory=dict)
    quality_distribution: Dict[str, int] = field(default_factory=dict)
    acs_superior_count: int = 0        # ACS quality > legacy quality
    acs_inferior_count: int = 0        # ACS quality < legacy quality
    acs_comparable_count: int = 0      # Roughly equal
    title_match_rate: float = 0.0      # ACS title contains legacy title or vice versa
    error_distribution: Dict[str, int] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    ready_for_on_mode: bool = False
    file_path: str = ""

    def to_dict(self) -> dict:
        return {
            "total_entries": self.total_entries,
            "acs_success_count": self.acs_success_count,
            "acs_failure_count": self.acs_failure_count,
            "acs_success_rate": round(self.acs_success_rate, 4),
            "acs_avg_completeness": round(self.acs_avg_completeness, 1),
            "acs_avg_body_len": round(self.acs_avg_body_len, 1),
            "legacy_avg_body_len": round(self.legacy_avg_body_len, 1),
            "parser_distribution": dict(
                sorted(self.parser_distribution.items(), key=lambda x: -x[1])
            ),
            "quality_distribution": dict(
                sorted(self.quality_distribution.items(), key=lambda x: -x[1])
            ),
            "acs_superior_count": self.acs_superior_count,
            "acs_inferior_count": self.acs_inferior_count,
            "acs_comparable_count": self.acs_comparable_count,
            "title_match_rate": round(self.title_match_rate, 4),
            "error_distribution": dict(
                sorted(self.error_distribution.items(), key=lambda x: -x[1])
            ),
            "recommendations": self.recommendations,
            "ready_for_on_mode": self.ready_for_on_mode,
            "file_path": self.file_path,
        }

    def summary_text(self) -> str:
        """Human-readable summary."""
        lines = [
            f"Shadow Analysis Report ({self.file_path})",
            f"  Total entries: {self.total_entries}",
            f"  ACS success rate: {self.acs_success_rate:.1%} ({self.acs_success_count}/{self.total_entries})",
            f"  ACS avg completeness: {self.acs_avg_completeness:.1f}%",
            f"  ACS avg body length: {self.acs_avg_body_len:.0f} chars",
            f"  Legacy avg body length: {self.legacy_avg_body_len:.0f} chars",
            f"  Quality comparison: ACS better={self.acs_superior_count} worse={self.acs_inferior_count} comparable={self.acs_comparable_count}",
            f"  Title match rate: {self.title_match_rate:.1%}",
            f"  Parser distribution: {self.parser_distribution}",
            f"  Quality distribution: {self.quality_distribution}",
            f"  Ready for on mode: {self.ready_for_on_mode}",
        ]
        for rec in self.recommendations:
            lines.append(f"  → {rec}")
        return "\n".join(lines)


class ShadowAnalyzer:
    """Analyzes ACS shadow comparison logs.

    Args:
        log_path: Path to acs_shadow.jsonl file
    """

    def __init__(self, log_path: str):
        self.log_path = os.path.abspath(log_path)

    def analyze(self) -> ShadowReport:
        """Parse shadow log and produce analysis report."""
        entries = self._read_entries()

        if not entries:
            report = ShadowReport(
                total_entries=0,
                file_path=self.log_path,
            )
            report.recommendations = ["No shadow data available — keep shadow mode."]
            return report

        report = ShadowReport(
            total_entries=len(entries),
            file_path=self.log_path,
        )

        # ── Counters ──
        acs_success = 0
        acs_completeness_sum = 0
        acs_body_len_sum = 0
        legacy_body_len_sum = 0
        parser_counts: Dict[str, int] = {}
        quality_counts: Dict[str, int] = {}
        error_counts: Dict[str, int] = {}
        title_matches = 0
        acs_better = 0
        acs_worse = 0
        acs_comparable = 0

        for entry in entries:
            if entry.get("acs_success"):
                acs_success += 1

            acs_completeness_sum += entry.get("acs_completeness", 0)
            acs_body_len_sum += entry.get("acs_body_len", 0)
            legacy_body_len_sum += entry.get("legacy_body_len", 0)

            # Parser distribution
            parser = entry.get("acs_parser", "unknown")
            parser_counts[parser] = parser_counts.get(parser, 0) + 1

            # Quality distribution
            quality = entry.get("acs_quality", "unknown")
            quality_counts[quality] = quality_counts.get(quality, 0) + 1

            # Error distribution
            acs_error = entry.get("acs_error", "")
            if acs_error:
                cat = acs_error[:50] or "unknown"
                error_counts[cat] = error_counts.get(cat, 0) + 1

            # Title match
            acs_title = (entry.get("acs_title") or "").strip()
            legacy_title = (entry.get("legacy_title") or "").strip()
            if acs_title and legacy_title:
                if acs_title in legacy_title or legacy_title in acs_title:
                    title_matches += 1

            # Quality comparison
            acs_qual = entry.get("acs_completeness", 0)
            legacy_qual = 0  # legacy doesn't track completeness directly
            # Fall back to body length as rough quality proxy
            acs_bl = entry.get("acs_body_len", 0)
            legacy_bl = entry.get("legacy_body_len", 0)
            if acs_bl > legacy_bl * 1.5:
                acs_better += 1
            elif legacy_bl > acs_bl * 1.5:
                acs_worse += 1
            else:
                acs_comparable += 1

        total = len(entries)

        report.acs_success_count = acs_success
        report.acs_failure_count = total - acs_success
        report.acs_success_rate = acs_success / total if total > 0 else 0.0
        report.acs_avg_completeness = acs_completeness_sum / total if total > 0 else 0.0
        report.acs_avg_body_len = acs_body_len_sum / total if total > 0 else 0.0
        report.legacy_avg_body_len = legacy_body_len_sum / total if total > 0 else 0.0
        report.parser_distribution = parser_counts
        report.quality_distribution = quality_counts
        report.error_distribution = error_counts
        report.title_match_rate = title_matches / total if total > 0 else 0.0
        report.acs_superior_count = acs_better
        report.acs_inferior_count = acs_worse
        report.acs_comparable_count = acs_comparable

        # ── Recommendations ──
        recommendations = []

        if total < 10:
            recommendations.append(
                "Sample size too small (< 10 entries) — keep shadow mode, gather more data"
            )
        elif report.acs_success_rate < 0.5:
            recommendations.append(
                f"ACS success rate too low ({report.acs_success_rate:.1%}) — investigate failures, keep shadow mode"
            )
        elif report.acs_success_rate >= 0.8 and report.acs_avg_completeness >= 50:
            recommendations.append(
                "ACS performs well — candidate for consideration, but do NOT auto-switch to on mode"
            )
        else:
            recommendations.append(
                "ACS performance is acceptable — continue shadow mode for monitoring"
            )

        if acs_better > acs_worse * 2 and total >= 50:
            recommendations.append(
                "ACS consistently outperforms legacy — after further validation, candidate for on mode"
            )
        elif acs_worse > acs_better * 2:
            recommendations.append(
                "ACS underperforms legacy — investigate inferior cases, keep shadow mode"
            )

        # Ready for on mode?
        report.ready_for_on_mode = (
            total >= 100 and
            report.acs_success_rate >= 0.85 and
            report.acs_avg_completeness >= 60 and
            acs_better >= acs_worse
        )
        if report.ready_for_on_mode:
            recommendations.append(
                "Metrics meet on-mode thresholds — but manual review STRONGLY recommended before switching"
            )
        else:
            recommendations.append(
                "Do NOT switch to on mode yet — metrics do not meet thresholds"
            )

        report.recommendations = recommendations
        return report

    def _read_entries(self) -> List[dict]:
        """Read JSONL entries from the shadow log file."""
        entries = []
        if not os.path.exists(self.log_path):
            return entries
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass
        return entries


def analyze_shadow_log(log_path: str) -> ShadowReport:
    """Convenience: analyze a shadow log and return the report."""
    return ShadowAnalyzer(log_path).analyze()
