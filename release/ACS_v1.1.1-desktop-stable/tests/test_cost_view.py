"""Tests for acs.dashboard.cost_view — cost display."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from acs.observability.cost_report import CostReport
from acs.dashboard.cost_view import CostView

class TestCostView:
    def test_get_summary(self):
        cr = CostReport()
        cr.record_call(url="http://x.com", tokens_prompt=100, tokens_completion=50)
        v = CostView(cr)
        s = v.get_summary()
        assert s["total_ai_calls"] == 1
        assert s["total_prompt_tokens"] == 100

    def test_markdown(self):
        cr = CostReport(run_id="v")
        cr.record_call(tokens_prompt=100, tokens_completion=50)
        v = CostView(cr)
        md = v.markdown()
        assert "AI Cost Report" in md
        assert "v" in md

    def test_from_audit_stats(self):
        stats = {"total_calls": 5, "successful_calls": 4, "failed_calls": 1, "total_tokens": 1000, "estimated_cost": 0.01}
        md = CostView.from_audit_stats(stats)
        assert "5" in md
        assert "0.01" in md

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
