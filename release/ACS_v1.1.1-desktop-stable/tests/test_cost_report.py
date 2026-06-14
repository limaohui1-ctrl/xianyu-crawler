"""Tests for acs.observability.cost_report — cost tracking, limit enforcement, export."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from acs.observability.cost_report import CostReport, CostSummary

class TestCostReport:
    def test_record_call(self):
        cr = CostReport(max_cost=1.00)
        cr.record_call(url="http://x.com", tokens_prompt=500, tokens_completion=200, success=True)
        s = cr.get_summary()
        assert s.total_ai_calls == 1
        assert s.total_prompt_tokens == 500
        assert s.estimated_cost > 0

    def test_failed_call_tracked(self):
        cr = CostReport()
        cr.record_call(success=False, error="timeout")
        s = cr.get_summary()
        assert s.failed_ai_calls == 1

    def test_record_blocked(self):
        cr = CostReport()
        cr.record_blocked()
        cr.record_blocked()
        s = cr.get_summary()
        assert s.ai_calls_blocked_by_policy == 2

    def test_cost_limit_below_max(self):
        cr = CostReport(max_cost=100.00)
        cr.record_call(tokens_prompt=1000, tokens_completion=500)
        assert not cr.check_limit()
        assert not cr.get_summary().cost_limit_reached

    def test_cost_limit_exceeded(self):
        cr = CostReport(max_cost=0.00001)
        cr.record_call(tokens_prompt=10000, tokens_completion=10000)
        assert cr.check_limit()
        assert cr.get_summary().cost_limit_reached

    def test_markdown_summary(self):
        cr = CostReport(run_id="test")
        cr.record_call(url="http://x.com", tokens_prompt=100, tokens_completion=50)
        md = cr.markdown_summary()
        assert "AI Cost Report" in md
        assert "test" in md
        assert "100" in md

    def test_to_json(self):
        cr = CostReport(run_id="test")
        cr.record_call(url="http://x.com", tokens_prompt=100, tokens_completion=50)
        j = cr.to_json()
        data = json.loads(j)
        assert data["run_id"] == "test"
        assert "entries" in data

    def test_json_save(self):
        import tempfile, shutil
        d = tempfile.mkdtemp()
        try:
            cr = CostReport()
            cr.record_call(tokens_prompt=100)
            path = os.path.join(d, "report.json")
            cr.save_json(path)
            assert os.path.exists(path)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_summary_to_dict(self):
        cr = CostReport(run_id="r1")
        d = cr.get_summary().to_dict()
        assert d["run_id"] == "r1"
        assert "estimated_cost" in d

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
