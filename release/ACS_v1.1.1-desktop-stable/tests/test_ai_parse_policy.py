"""Tests for acs.strategy.ai_parse_policy — invocation conditions, cost control, per-URL limits."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from acs.strategy.ai_parse_policy import AIParsePolicy, AIParseDecision
from acs.strategy.cost_controller import CostController


class TestAIParsePolicy:
    def test_default_disabled_when_master_off(self):
        p = AIParsePolicy(ai_fallback_enabled=False)
        d = p.should_invoke_ai_parser(url="http://x.com")
        assert not d.should_invoke
        assert "disabled" in d.reason.lower()

    def test_user_requested_overrides_disabled(self):
        p = AIParsePolicy(ai_fallback_enabled=False)
        d = p.should_invoke_ai_parser(url="http://x.com", user_requested=True)
        assert d.should_invoke

    def test_max_ai_calls_per_run(self):
        p = AIParsePolicy(max_ai_calls_per_run=3, max_ai_calls_per_url=10)
        for i in range(3):
            d = p.should_invoke_ai_parser(url=f"http://x.com/p{i}", user_requested=True)
            assert d.should_invoke
            p.record_ai_call(f"http://x.com/p{i}")
        d = p.should_invoke_ai_parser(url="http://x.com/new", user_requested=True)
        assert not d.should_invoke
        assert d.max_cost_exceeded

    def test_per_url_limit(self):
        p = AIParsePolicy(max_ai_calls_per_url=1)
        d = p.should_invoke_ai_parser(url="http://x.com", user_requested=True)
        assert d.should_invoke
        p.record_ai_call("http://x.com")
        d = p.should_invoke_ai_parser(url="http://x.com", user_requested=True)
        assert not d.should_invoke
        # Different URL should be OK
        d = p.should_invoke_ai_parser(url="http://y.com", user_requested=True)
        assert d.should_invoke

    def test_all_parsers_failed_triggers_ai(self):
        p = AIParsePolicy()
        class FakeAttempt: pass
        a1, a2 = FakeAttempt(), FakeAttempt()
        a1.success, a2.success = False, False
        a1.parser_name, a2.parser_name = "css", "fallback"
        d = p.should_invoke_ai_parser(url="http://x.com", parse_attempts=[a1, a2])
        assert d.should_invoke
        assert "failed" in d.reason.lower()

    def test_missing_critical_fields_triggers_ai(self):
        p = AIParsePolicy()
        d = p.should_invoke_ai_parser(url="http://x.com", missing_critical_fields=["title", "price"])
        assert d.should_invoke
        assert "title" in d.reason

    def test_no_trigger_no_invoke(self):
        p = AIParsePolicy()
        class FA: pass
        a = FA(); a.success = True; a.parser_name = "css"
        d = p.should_invoke_ai_parser(url="http://x.com", parse_attempts=[a])
        assert not d.should_invoke

    def test_record_ai_call_tracks_tokens(self):
        p = AIParsePolicy()
        p.record_ai_call("http://x.com", prompt_tokens=500, completion_tokens=200)
        assert p.total_ai_calls == 1
        assert p.total_ai_tokens == 700
        assert p.estimated_ai_cost > 0

    def test_get_stats(self):
        p = AIParsePolicy(max_ai_calls_per_run=50, max_ai_calls_per_url=2)
        p.record_ai_call("http://a.com", 100, 50)
        p.record_ai_call("http://b.com", 200, 100)
        s = p.get_stats()
        assert s["total_ai_calls"] == 2
        assert s["unique_urls"] == 2
        assert s["max_ai_calls_per_run"] == 50

    def test_reset(self):
        p = AIParsePolicy()
        p.record_ai_call("x", 100, 50)
        p.reset()
        assert p.total_ai_calls == 0
        assert p.total_ai_tokens == 0
        assert p.estimated_ai_cost == 0.0

    def test_decision_to_dict(self):
        d = AIParseDecision(should_invoke=True, reason="test", ai_calls_remaining=5)
        dd = d.to_dict()
        assert dd["should_invoke"] is True
        assert dd["reason"] == "test"
        assert dd["ai_calls_remaining"] == 5

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
