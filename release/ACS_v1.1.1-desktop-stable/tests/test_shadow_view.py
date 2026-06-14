"""Tests for acs.dashboard.shadow_view — shadow stats display."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from acs.dashboard.shadow_view import ShadowView

class TestShadowView:
    def test_get_summary_from_stats(self):
        stats = {"total_entries": 10, "acs_success_rate": 0.85, "ready_for_on_mode": False}
        v = ShadowView(shadow_stats=stats)
        s = v.get_summary()
        assert s["total_entries"] == 10

    def test_markdown_with_data(self):
        stats = {"total_entries": 5, "acs_success_rate": 0.8, "acs_superior_count": 3, "acs_inferior_count": 1, "acs_comparable_count": 1, "ready_for_on_mode": False, "acs_avg_completeness": 60}
        v = ShadowView(shadow_stats=stats)
        md = v.markdown()
        assert "Shadow Comparison" in md
        assert "80.0%" in md
        assert "False" in md

    def test_markdown_empty(self):
        v = ShadowView(shadow_stats={})
        md = v.markdown()
        assert "No data" in md

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
