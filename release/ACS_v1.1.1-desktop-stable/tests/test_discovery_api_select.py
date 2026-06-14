"""Tests: discovery API select — blocked URLs rejected."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.web.local_server import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_select_requires_batch_id(client):
    r = client.post("/api/discovery/select", json={"selected_urls": ["https://x.com"]})
    assert r.status_code == 400


def test_select_nonexistent_batch(client):
    r = client.post("/api/discovery/select", json={
        "batch_id": "nonexistent_99999", "selected_urls": ["https://x.com"]
    })
    assert r.status_code == 404


def test_select_blocked_rejected(client):
    # First run discovery
    r = client.post("/api/discovery/run", json={
        "provider": "mock", "topic": "amazon", "keywords": ["amazon"], "limit": 50
    })
    assert r.status_code == 200
    batch = r.get_json()
    # Find a blocked URL
    blocked = [c for c in batch["candidates"] if c["compliance_status"] == "blocked"]
    if blocked:
        r = client.post("/api/discovery/select", json={
            "batch_id": batch["batch_id"],
            "selected_urls": [blocked[0]["url"]],
        })
        assert r.status_code == 403
        assert "blocked" in r.get_json()["error"].lower()


def test_select_allowed_works(client):
    r = client.post("/api/discovery/run", json={
        "provider": "mock", "topic": "治理", "keywords": ["VOCs"], "limit": 50
    })
    batch = r.get_json()
    allowed = [c for c in batch["candidates"] if c["compliance_status"] == "allowed"]
    assert len(allowed) >= 1
    r = client.post("/api/discovery/select", json={
        "batch_id": batch["batch_id"],
        "selected_urls": [allowed[0]["url"]],
    })
    assert r.status_code == 200
    assert r.get_json()["selected_count"] >= 1


def test_select_forbidden_headers(client):
    r = client.post("/api/discovery/select",
                    json={"batch_id": "x", "selected_urls": []},
                    headers={"Authorization": "Bearer xyz"})
    assert r.status_code == 403
