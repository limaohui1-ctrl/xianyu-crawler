"""Tests for acs.strategy.strategy_engine — mode switching and strategy decisions."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from acs.strategy.strategy_engine import StrategyEngine, StrategyState
from acs.strategy.crawl_modes import CrawlMode, MODE_DEFAULTS


class TestStrategyEngine:

    def test_default_mode(self):
        engine = StrategyEngine()
        assert engine.active_mode == CrawlMode.FULL

    def test_set_mode(self):
        engine = StrategyEngine()
        engine.set_mode(CrawlMode.CONSERVATIVE, reason="test")
        assert engine.active_mode == CrawlMode.CONSERVATIVE
        state = engine.get_state()
        assert len(state.transition_history) == 1
        assert state.transition_history[0]["from"] == "full"
        assert state.transition_history[0]["to"] == "conservative"

    def test_mode_updates_sub_components(self):
        engine = StrategyEngine()
        engine.set_mode(CrawlMode.FAST)
        cfg = MODE_DEFAULTS[CrawlMode.FAST]
        assert engine.retry_policy.max_retries == cfg.max_retries
        assert engine.retry_policy.backoff_base == cfg.retry_backoff_base

    def test_rate_limiter_updated_on_mode_change(self):
        engine = StrategyEngine()
        engine.set_mode(CrawlMode.CONSERVATIVE)
        s = engine.rate_limiter.stats
        assert s["global_rps"] == 0.3

    def test_should_retry_delegates_to_policy(self):
        engine = StrategyEngine()
        d = engine.should_retry(retry_count=0, status_code=429)
        assert d.should_retry
        d2 = engine.should_retry(retry_count=0, status_code=404)
        assert not d2.should_retry

    def test_acquire_rate_limit(self):
        engine = StrategyEngine()
        engine.set_mode(CrawlMode.FAST)
        waited = engine.acquire_rate_limit("example.com", timeout=0.5)
        assert waited >= 0

    def test_record_request(self):
        engine = StrategyEngine()
        engine.record_request("http://a.com", success=True)
        engine.record_request("http://b.com", success=False)
        s = engine.get_state()
        assert s.cost_summary["total_requests"] == 2
        assert s.cost_summary["total_success"] == 1
        assert s.cost_summary["total_failures"] == 1

    def test_record_shadow_parse(self):
        engine = StrategyEngine()
        engine.record_shadow_parse()
        engine.record_shadow_parse()
        s = engine.get_state()
        assert s.cost_summary["shadow_parse_count"] == 2

    def test_record_shadow_comparison(self):
        engine = StrategyEngine()
        engine.record_shadow_comparison("http://a.com", acs_quality=80, legacy_quality=50)
        engine.record_shadow_comparison("http://b.com", acs_quality=30, legacy_quality=70)
        engine.record_shadow_comparison("http://c.com", acs_quality=50, legacy_quality=55)
        stats = engine.get_shadow_stats()
        assert stats["superior"] == 1
        assert stats["inferior"] == 1
        assert stats["equal"] == 1
        assert stats["total_compared"] == 3

    def test_check_and_adapt_degrade(self):
        engine = StrategyEngine()
        engine.cost_controller.max_failure_rate = 0.1
        for _ in range(10):
            engine.record_request("url", success=False)
        action = engine.check_and_adapt()
        assert action == "degraded"
        assert engine.active_mode == CrawlMode.DEGRADED

    def test_check_and_adapt_noop(self):
        engine = StrategyEngine()
        engine.record_request("url", success=True)
        action = engine.check_and_adapt()
        assert action is None
        assert engine.active_mode == CrawlMode.FULL

    def test_should_stop_on_absolute_failures(self):
        engine = StrategyEngine()
        engine.cost_controller.max_total_failures = 5
        for _ in range(5):
            engine.record_request("url", success=False)
        assert engine.should_stop

    def test_get_state_comprehensive(self):
        engine = StrategyEngine()
        engine.record_request("url", success=True)
        state = engine.get_state()
        assert state.active_mode == "full"
        assert state.mode_config is not None
        assert state.cost_summary is not None
        assert state.rate_limiter_stats is not None

    def test_reset(self):
        engine = StrategyEngine()
        engine.set_mode(CrawlMode.FAST)
        engine.record_request("url", success=False)
        engine.record_shadow_parse()
        engine.reset()
        assert engine.active_mode == CrawlMode.FULL
        s = engine.get_state()
        assert s.cost_summary["total_requests"] == 0

    def test_shadow_recommendation_insufficient_data(self):
        engine = StrategyEngine()
        rec = engine.get_shadow_stats()["recommendation"]
        assert "insufficient_data" in rec

    def test_shadow_recommendation_acs_better(self):
        engine = StrategyEngine()
        for _ in range(50):
            engine.record_shadow_comparison("url", acs_quality=80, legacy_quality=50)
        rec = engine.get_shadow_stats()["recommendation"]
        assert "acs_performs_better" in rec or "insufficient_data" in rec

    def test_transition_history_capped(self):
        engine = StrategyEngine()
        for i in range(60):
            engine.set_mode(CrawlMode.FULL if i % 2 == 0 else CrawlMode.FAST, f"test_{i}")
        state = engine.get_state()
        assert len(state.transition_history) <= 50

    def test_default_max_retries_from_mode(self):
        engine = StrategyEngine()
        assert engine.retry_policy.max_retries == MODE_DEFAULTS[CrawlMode.FULL].max_retries
        engine.set_mode(CrawlMode.FAST)
        assert engine.retry_policy.max_retries == MODE_DEFAULTS[CrawlMode.FAST].max_retries


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
