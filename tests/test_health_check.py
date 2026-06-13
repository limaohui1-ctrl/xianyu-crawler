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

def test_check_function_registered():
    hc.CHECKS.clear()
    from acs.ops.health_check import check
    ok = check("test_check", lambda: (True, "ok"))
    assert ok is True
    assert len(hc.CHECKS) == 1
    assert hc.CHECKS[0]["name"] == "test_check"
