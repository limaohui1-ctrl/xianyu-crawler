"""Tests for health check."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import acs.ops.health_check as hc

def test_check_sqlite():
    ok, msg = hc._check_sqlite("acs_data/reviews.db")
    assert isinstance(ok, bool)
    assert isinstance(msg, str)

def test_check_api_key_env():
    ok, msg = hc._check_api_key_env_only()
    assert isinstance(ok, bool)

def test_acs_mode_env():
    old = os.environ.get("ACS_MODE")
    os.environ["ACS_MODE"] = "shadow"
    assert os.environ.get("ACS_MODE") == "shadow"
    if old is not None: os.environ["ACS_MODE"] = old
    else: os.environ.pop("ACS_MODE", None)

def test_check_function():
    hc.CHECKS.clear()
    ok = hc.check("test", lambda: (True, "pass"))
    assert ok is True
    assert len(hc.CHECKS) == 1
    assert hc.CHECKS[0]["name"] == "test"
    assert hc.CHECKS[0]["status"] == "PASS"

def test_check_fail_function():
    hc.CHECKS.clear()
    ok = hc.check("fail", lambda: (False, "bad"))
    assert ok is False
    assert hc.CHECKS[0]["status"] == "FAIL"

def test_check_exception():
    hc.CHECKS.clear()
    ok = hc.check("ex", lambda: 1/0)
    assert ok is False
    assert hc.CHECKS[0]["status"] == "FAIL"

def test_health_run_includes_chart_check():
    hc.run()
    names = [c["name"] for c in hc.CHECKS]
    assert any("Dashboard" in n for n in names)
    assert any("Chart" in n for n in names)
    assert any("cron" in n.lower() for n in names)

def test_health_check_has_required_checks():
    hc.run()
    names = [c["name"] for c in hc.CHECKS]
    required = ["ACS_MODE", "Adapter", "Self-test", "Dashboard", "Chart", "SQLite"]
    for r in required:
        assert any(r.lower() in n.lower() for n in names), f"Missing check: {r}"
