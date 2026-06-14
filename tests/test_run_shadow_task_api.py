"""Tests: /api/tasks/run-shadow endpoint."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.web.local_server import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_run_shadow_returns_run_id(client):
    r = client.post("/api/tasks/run-shadow", json={
        "task_id": "test_task", "max_urls": 5, "rate_limit": 0.5
    })
    assert r.status_code == 200
    d = r.get_json()
    assert d["run_id"].startswith("shadow_run_")
    assert d["mode"] == "shadow"


def test_run_shadow_mode_is_shadow(client):
    r = client.post("/api/tasks/run-shadow", json={"max_urls": 3})
    assert r.get_json()["mode"] == "shadow"


def test_run_shadow_forbidden_headers(client):
    r = client.post("/api/tasks/run-shadow", json={},
                    headers={"Authorization": "Bearer xyz"})
    assert r.status_code == 403


def test_run_shadow_path_safety(client):
    r = client.post("/api/tasks/run-shadow", json={
        "url_file": "C:\\Windows\\System32\\evil.txt", "max_urls": 3
    })
    assert r.status_code == 403
