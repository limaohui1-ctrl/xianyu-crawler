"""Tests: local server path safety — rejects external paths."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.web.local_server import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_rejects_windows_system_path(client):
    r = client.post("/api/tasks/run-shadow", json={
        "url_file": "C:\\Windows\\System32\\drivers\\etc\\hosts", "max_urls": 1
    })
    assert r.status_code == 403


def test_rejects_unix_absolute_path(client):
    r = client.post("/api/tasks/run-shadow", json={
        "url_file": "/etc/passwd", "max_urls": 1
    })
    assert r.status_code == 403


def test_rejects_parent_traversal(client):
    r = client.post("/api/tasks/run-shadow", json={
        "url_file": "../outside/file.txt", "max_urls": 1
    })
    assert r.status_code == 403


def test_allows_valid_acs_data_path(client):
    import tempfile, os
    acs_data = os.path.abspath("acs_data")
    os.makedirs(acs_data, exist_ok=True)
    valid = os.path.join(acs_data, "test_urls.txt")
    with open(valid, "w") as f:
        f.write("https://example.com\n")
    r = client.post("/api/tasks/run-shadow", json={
        "url_file": valid, "max_urls": 2
    })
    assert r.status_code == 200
    assert r.get_json()["mode"] == "shadow"
