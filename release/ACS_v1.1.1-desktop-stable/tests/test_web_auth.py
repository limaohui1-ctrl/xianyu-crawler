"""Tests for web auth — local-only, no key exposure."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.web.auth import auth_status

def test_auth_status():
    s = auth_status()
    assert "auth_enabled" in s
    assert s["method"] in ("none", "token")

def test_no_api_key_in_auth_module():
    import acs.web.auth as m
    source = open(m.__file__, encoding="utf-8").read()
    assert "sk-" not in source
    assert "authorization" not in source.lower()

def test_dashboard_pages_no_key():
    from acs.web.app import app
    app.config["TESTING"] = True
    c = app.test_client()
    for route in ["/", "/shadow", "/cost", "/reviews", "/audit"]:
        r = c.get(route)
        html = r.data.decode("utf-8", errors="replace")
        assert "sk-" not in html
        assert "Bearer" not in html
