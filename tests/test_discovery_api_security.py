"""Tests: discovery API security — no auth headers, no key leaks."""
import sys, os, json, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.web.local_server import app, _security_check


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_security_check_blocks_authorization():
    """Test _security_check directly with a mock environ."""
    with app.test_request_context("/api/health", headers={"Authorization": "Bearer xyz"}):
        blocked, reason = _security_check()
        assert blocked
        assert "authorization" in reason.lower()


def test_security_check_blocks_body_keyword(client):
    """Test that body containing 'token=' is blocked."""
    r = client.post("/api/discovery/run",
                    data='{"provider":"mock","note":"token=secret123"}',
                    content_type="application/json")
    assert r.status_code == 403


def test_security_check_allows_clean_request():
    with app.test_request_context("/api/health"):
        blocked, reason = _security_check()
        assert not blocked


def test_security_check_blocks_cookie_header():
    with app.test_request_context("/api/health", headers={"Cookie": "session=abc"}):
        blocked, reason = _security_check()
        assert blocked


def test_endpoint_blocks_authorization_header(client):
    r = client.post("/api/discovery/run",
                    json={"provider": "mock"},
                    headers={"Authorization": "Bearer token"})
    assert r.status_code == 403


def test_no_key_in_health(client):
    r = client.get("/api/health")
    j = json.dumps(r.get_json())
    assert "sk-" not in j
    assert "Bearer" not in j


def test_no_key_in_discovery_response(client):
    r = client.post("/api/discovery/run", json={
        "provider": "mock", "topic": "test", "keywords": ["test"], "limit": 5
    })
    j = json.dumps(r.get_json())
    assert "sk-" not in j
    assert "Bearer" not in j
    assert "api_key" not in j.lower()


def test_blocked_providers_all(client):
    blocked = ["search", "google", "bing", "serpapi", "serper"]
    for p in blocked:
        r = client.post("/api/discovery/run", json={"provider": p})
        assert r.status_code == 403, f"Provider {p} should be 403, got {r.status_code}"
