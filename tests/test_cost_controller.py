"""Tests for acs.strategy.cost_controller — resource tracking and limits."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from acs.strategy.cost_controller import CostController, CostSummary


class TestCostController:

    def test_record_request(self):
        cc = CostController()
        cc.record_request()
        cc.record_success()
        s = cc.get_summary()
        assert s.total_requests == 1
        assert s.total_success == 1

    def test_record_failure(self):
        cc = CostController()
        cc.record_request()
        cc.record_failure("http://example.com", "timeout")
        s = cc.get_summary()
        assert s.total_failures == 1
        assert s.total_requests == 1

    def test_record_retry(self):
        cc = CostController()
        cc.record_retry()
        cc.record_retry()
        s = cc.get_summary()
        assert s.total_retries == 2

    def test_record_shadow(self):
        cc = CostController()
        cc.record_shadow_parse()
        cc.record_shadow_parse()
        s = cc.get_summary()
        assert s.shadow_parse_count == 2

    def test_failure_rate(self):
        cc = CostController()
        for _ in range(5):
            cc.record_request()
            cc.record_success()
        for _ in range(5):
            cc.record_request()
            cc.record_failure("url", "err")
        rate = cc.failure_rate
        assert 0.4 < rate < 0.6  # 5/10 = 0.5

    def test_failure_rate_zero_when_no_requests(self):
        cc = CostController()
        assert cc.failure_rate == 0.0

    def test_should_degrade_on_high_failure(self):
        cc = CostController(max_failure_rate=0.2)
        # 10 successes, 5 failures → 0.33 > 0.2
        for _ in range(10):
            cc.record_request()
            cc.record_success()
        for _ in range(5):
            cc.record_request()
            cc.record_failure("url", "err")
        assert cc.should_degrade

    def test_should_degrade_on_max_requests(self):
        cc = CostController(max_requests=5)
        for _ in range(5):
            cc.record_request()
            cc.record_success()
        assert cc.should_degrade

    def test_no_degrade_below_threshold(self):
        cc = CostController(max_failure_rate=0.5)
        for _ in range(10):
            cc.record_request()
            cc.record_success()
        cc.record_request()
        cc.record_failure("url", "err")
        assert not cc.should_degrade

    def test_should_stop_absolute_failures(self):
        cc = CostController(max_total_failures=3)
        for _ in range(3):
            cc.record_request()
            cc.record_failure("url", "err")
        assert cc.should_stop

    def test_no_stop_below_absolute(self):
        cc = CostController(max_total_failures=10)
        for _ in range(3):
            cc.record_request()
            cc.record_failure("url", "err")
        assert not cc.should_stop

    def test_mark_degraded(self):
        cc = CostController()
        cc.mark_degraded()
        assert cc.should_degrade

    def test_mark_stopped(self):
        cc = CostController()
        cc.mark_stopped("test reason")
        assert cc.should_stop

    def test_get_summary_text(self):
        cc = CostController()
        cc.record_request()
        cc.record_success()
        text = cc.get_summary_text()
        assert "NORMAL" in text
        assert "req=1" in text

    def test_get_summary_dict(self):
        cc = CostController()
        d = cc.get_summary().to_dict()
        assert "total_requests" in d
        assert "failure_rate" in d
        assert "should_degrade" in d
        assert "should_stop" in d

    def test_get_failure_details(self):
        cc = CostController()
        cc.record_failure("http://a.com", "timeout")
        cc.record_failure("http://b.com", "404")
        details = cc.get_failure_details()
        assert len(details) == 2
        assert details[0]["url"] == "http://a.com"

    def test_reset(self):
        cc = CostController()
        cc.record_request()
        cc.record_failure("url", "err")
        cc.mark_degraded()
        cc.reset()
        s = cc.get_summary()
        assert s.total_requests == 0
        assert not cc.should_degrade
        assert not cc.should_stop

    def test_failure_details_capped(self):
        cc = CostController()
        for i in range(600):
            cc.record_failure(f"url_{i}", "err")
        details = cc.get_failure_details(limit=500)
        assert len(details) == 500
        assert details[-1]["url"] == "url_499"

    def test_degrade_threshold_min_requests(self):
        """Should NOT degrade on first few failures."""
        cc = CostController(max_failure_rate=0.1)
        cc.record_request()
        cc.record_failure("url", "err")
        assert not cc.should_degrade  # < 10 requests, ignore rate

    def test_requests_per_minute(self):
        cc = CostController()
        for _ in range(10):
            cc.record_request()
            cc.record_success()
        s = cc.get_summary()
        assert s.requests_per_minute > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
