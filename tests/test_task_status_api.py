"""Tests: /api/tasks/status endpoint."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.web.local_server import app, _task_state


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_status_requires_run_id(client):
    r = client.get("/api/tasks/status")
    assert r.status_code == 400


def test_status_not_found(client):
    r = client.get("/api/tasks/status?run_id=nonexistent")
    d = r.get_json()
    assert d["status"] == "not_found"


def test_status_returns_state(client):
    rid = "test_run_123"
    _task_state(rid, status="running", total=10, success=3, failed=0, progress=0.3)
    r = client.get("/api/tasks/status?run_id=" + rid)
    d = r.get_json()
    assert d["status"] == "running"
    assert d["total"] == 10
    assert d["success"] == 3


def test_status_updates(client):
    rid = "test_run_456"
    _task_state(rid, status="running", total=5)
    _task_state(rid, status="completed", success=5, progress=1.0)
    r = client.get("/api/tasks/status?run_id=" + rid)
    d = r.get_json()
    assert d["status"] == "completed"
    assert d["progress"] == 1.0
