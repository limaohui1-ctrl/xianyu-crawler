"""Tests for SearXNG API control endpoints."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def client():
    from acs.web.app import app
    app.config["TESTING"] = True
    return app.test_client()


def test_api_searxng_status(client):
    r = client.get("/api/search/searxng/status")
    assert r.status_code in (200, 500)
    data = r.get_json()
    assert "status" in data


def test_api_searxng_action_rejects_unknown(client):
    r = client.post("/api/search/searxng/delete_everything",
                    json={},
                    headers={"X-ACS-Auth": "test"})
    assert r.status_code in (400, 401, 403)


def test_api_searxng_action_whitelist():
    """Only allowed actions should be in the whitelist."""
    from acs.web.app import _SEARXNG_ACTIONS
    assert "status" in _SEARXNG_ACTIONS
    assert "setup" in _SEARXNG_ACTIONS
    assert "start" in _SEARXNG_ACTIONS
    assert "restart" in _SEARXNG_ACTIONS
    # No dangerous actions
    for forbidden in ["delete", "rm", "exec", "sh", "bash", "cmd", "run", "stop", "kill"]:
        assert forbidden not in _SEARXNG_ACTIONS
