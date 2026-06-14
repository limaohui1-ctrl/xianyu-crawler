"""Tests for alert rules engine."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.ops.alert_rules import AlertEngine, Alert

def test_empty_no_alerts():
    e = AlertEngine()
    a = e.check({})
    assert len(a) == 0

def test_ai_fail_rate_triggered():
    e = AlertEngine()
    a = e.check({"ai_fail_rate": 0.5})
    assert any(x.rule == "ai_fail_rate" for x in a)

def test_ai_fail_rate_not_triggered():
    e = AlertEngine()
    a = e.check({"ai_fail_rate": 0.1})
    assert not any(x.rule == "ai_fail_rate" for x in a)

def test_cost_near_limit():
    e = AlertEngine()
    a = e.check({"cost_ratio": 0.9})
    assert any(x.rule == "cost_near_limit" for x in a)

def test_shadow_drop():
    e = AlertEngine()
    a = e.check({"shadow_success_rate": 0.3})
    assert any(x.rule == "shadow_success_drop" for x in a)

def test_pending_backlog():
    e = AlertEngine()
    a = e.check({"pending_reviews": 30})
    assert any(x.rule == "pending_backlog" for x in a)

def test_alert_to_dict():
    a = Alert("test", "high", "msg", 0.5, 0.3, True)
    d = a.to_dict()
    assert d["rule"] == "test"
    assert d["severity"] == "high"
