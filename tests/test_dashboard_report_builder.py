"""Tests for acs.dashboard.report_builder — aggregate report generation."""
import sys, os, tempfile, shutil, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from acs.dashboard.report_builder import ReportBuilder

class TestDashboardReportBuilder:
    def test_build_empty(self):
        b = ReportBuilder()
        r = b.build()
        assert r.shadow == {}
        assert r.cost == {}
        assert r.ai_parser == {}
        assert r.reviews == {}
        assert r.structure == {}
        assert r.safety["acs_mode"] in ("shadow", "")
        assert r.safety["auto_apply"] == False

    def test_build_markdown(self):
        b = ReportBuilder()
        md = b.build_markdown()
        assert "ACS Dashboard Report" in md
        # Safety section includes ACS_MODE info
        assert "Shadow" in md

    def test_build_dict(self):
        b = ReportBuilder()
        d = b.build_dict()
        assert "shadow" in d
        assert "safety" in d
        assert d["safety"]["auto_apply"] == False

    def test_to_dict_method(self):
        b = ReportBuilder()
        r = b.build()
        d = r.to_dict()
        assert "generated_at" in d
        assert isinstance(d["shadow"], dict)

    def test_markdown_with_string_data(self):
        b = ReportBuilder()
        md = b.build()
        text = md.markdown()
        assert "0.0%" in text or "0" in text  # default values present
        assert "# ACS Dashboard Report" in text

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
