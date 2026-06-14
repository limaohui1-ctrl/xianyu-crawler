"""Tests: task creation from selected candidates."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.web.local_server import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_create_task_returns_id(client):
    r = client.post("/api/tasks/create-from-selected", json={"batch_id": "any"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["task_id"]
    assert d["mode"] == "shadow"
    assert d["acs_mode_on"] is False
    assert "shadow_batch" in d["command_preview"]


def test_create_task_mode_is_shadow(client):
    r = client.post("/api/tasks/create-from-selected", json={})
    d = r.get_json()
    assert d["mode"] == "shadow"


def test_create_task_command_preview(client):
    r = client.post("/api/tasks/create-from-selected", json={})
    d = r.get_json()
    assert "--rate-limit" in d["command_preview"]


def test_create_task_forbidden_headers(client):
    r = client.post("/api/tasks/create-from-selected",
                    json={}, headers={"Authorization": "Bearer xyz"})
    assert r.status_code == 403
