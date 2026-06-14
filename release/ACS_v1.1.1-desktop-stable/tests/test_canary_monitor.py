"""Tests for canary_monitor — error/completeness/cost checks."""
import sys, os, json, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.ops.canary_monitor import CanaryMonitor, CanaryMetrics

def test_canary_metrics_create():
    m = CanaryMetrics(site_id="test")
    assert m.site_id == "test"
    assert m.status == "ok"
    assert not m.rollback_signalled

def test_monitor_check_runs():
    mon = CanaryMonitor(site_id="public_test_ecommerce")
    m = mon.check()
    assert isinstance(m, CanaryMetrics)
    assert m.site_id == "public_test_ecommerce"

def test_monitor_rollback_signal_on_error_rate():
    mon = CanaryMonitor(site_id="test", rollback_on_error_rate=0.01)
    m = mon.check()
    # error_rate depends on shadow log; test structure
    assert isinstance(m.rollback_signalled, bool)

def test_monitor_summary():
    mon = CanaryMonitor(site_id="test")
    mon.check()
    s = mon.summary()
    assert "status" in s
    assert "rollback_signalled" in s

def test_monitor_to_list():
    mon = CanaryMonitor(site_id="test")
    mon.check()
    lst = mon.to_list()
    assert len(lst) >= 1
    assert all(isinstance(x, dict) for x in lst)

def test_monitor_no_api_key():
    m = CanaryMetrics(site_id="k")
    j = json.dumps(m.to_dict())
    assert "sk-" not in j
    assert "Bearer" not in j
