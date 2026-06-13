"""Tests for acs.observability.shadow_analyzer — shadow log analysis."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import json
import tempfile
import shutil

from acs.observability.shadow_analyzer import (
    ShadowAnalyzer, ShadowReport, analyze_shadow_log,
)


@pytest.fixture
def shadow_log():
    """Create a temporary shadow JSONL file with sample data."""
    d = tempfile.mkdtemp()
    log_path = os.path.join(d, "acs_shadow.jsonl")

    entries = [
        {
            "ts": "2026-06-13 21:00:00",
            "url": "https://example.com/page1",
            "mode": "shadow",
            "legacy_title": "Product A",
            "legacy_body_len": 200,
            "legacy_error": "",
            "acs_success": True,
            "acs_parser": "css",
            "acs_title": "Product A",
            "acs_body_len": 350,
            "acs_quality": "medium",
            "acs_completeness": 55,
            "acs_error": "",
        },
        {
            "ts": "2026-06-13 21:00:01",
            "url": "https://example.com/page2",
            "mode": "shadow",
            "legacy_title": "Product B",
            "legacy_body_len": 150,
            "legacy_error": "",
            "acs_success": True,
            "acs_parser": "jsonld",
            "acs_title": "Structured Product B",
            "acs_body_len": 500,
            "acs_quality": "high",
            "acs_completeness": 78,
            "acs_error": "",
        },
        {
            "ts": "2026-06-13 21:00:02",
            "url": "https://example.com/page3",
            "mode": "shadow",
            "legacy_title": "Product C",
            "legacy_body_len": 100,
            "legacy_error": "",
            "acs_success": False,
            "acs_parser": "fallback",
            "acs_title": "",
            "acs_body_len": 0,
            "acs_quality": "low",
            "acs_completeness": 0,
            "acs_error": "No content extracted",
        },
        {
            "ts": "2026-06-13 21:00:03",
            "url": "https://example.com/page4",
            "mode": "shadow",
            "legacy_title": "Product D",
            "legacy_body_len": 80,
            "legacy_error": "",
            "acs_success": True,
            "acs_parser": "css",
            "acs_title": "Product D — Store",
            "acs_body_len": 120,
            "acs_quality": "medium",
            "acs_completeness": 44,
            "acs_error": "",
        },
    ]

    with open(log_path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    yield log_path
    shutil.rmtree(d, ignore_errors=True)


class TestShadowAnalyzer:

    def test_analyze_empty(self):
        d = tempfile.mkdtemp()
        try:
            path = os.path.join(d, "nonexistent.jsonl")
            report = analyze_shadow_log(path)
            assert report.total_entries == 0
            assert len(report.recommendations) > 0
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_analyze_with_data(self, shadow_log):
        report = analyze_shadow_log(shadow_log)
        assert report.total_entries == 4
        assert report.acs_success_count == 3
        assert report.acs_failure_count == 1
        assert report.acs_success_rate == 0.75

    def test_avg_completeness(self, shadow_log):
        report = analyze_shadow_log(shadow_log)
        expected = (55 + 78 + 0 + 44) / 4
        assert abs(report.acs_avg_completeness - expected) < 0.1

    def test_parser_distribution(self, shadow_log):
        report = analyze_shadow_log(shadow_log)
        assert report.parser_distribution["css"] == 2
        assert report.parser_distribution["jsonld"] == 1
        assert report.parser_distribution["fallback"] == 1

    def test_quality_distribution(self, shadow_log):
        report = analyze_shadow_log(shadow_log)
        assert report.quality_distribution["medium"] == 2
        assert report.quality_distribution["high"] == 1
        assert report.quality_distribution["low"] == 1

    def test_error_distribution(self, shadow_log):
        report = analyze_shadow_log(shadow_log)
        assert len(report.error_distribution) >= 1

    def test_title_match_rate(self, shadow_log):
        report = analyze_shadow_log(shadow_log)
        # Product A matches, Product C has no ACS title, Product D partial
        assert 0.0 < report.title_match_rate < 1.0

    def test_not_ready_for_on_mode_small_sample(self, shadow_log):
        report = analyze_shadow_log(shadow_log)
        assert not report.ready_for_on_mode

    def test_recommendations_present(self, shadow_log):
        report = analyze_shadow_log(shadow_log)
        assert len(report.recommendations) >= 1

    def test_summary_text(self, shadow_log):
        report = analyze_shadow_log(shadow_log)
        text = report.summary_text()
        assert "Shadow Analysis Report" in text
        assert "Total entries: 4" in text
        assert "ACS success rate:" in text

    def test_to_dict(self, shadow_log):
        report = analyze_shadow_log(shadow_log)
        d = report.to_dict()
        assert d["total_entries"] == 4
        assert "parser_distribution" in d
        assert "recommendations" in d

    def test_report_dataclass_defaults(self):
        report = ShadowReport()
        assert report.total_entries == 0
        assert report.acs_success_rate == 0.0
        assert not report.ready_for_on_mode

    def test_analyze_with_invalid_json_skipped(self):
        d = tempfile.mkdtemp()
        try:
            log_path = os.path.join(d, "bad.jsonl")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write('{"valid": "entry", "acs_success": true}\n')
                f.write('not valid json\n')
                f.write('{"also": "valid"}\n')
            report = analyze_shadow_log(log_path)
            assert report.total_entries == 2  # Invalid line skipped
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
