"""Tests: /api/results/export endpoint."""
import sys, os, json, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.web.local_server import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_export_json(client):
    r = client.post("/api/results/export", json={"format": "json"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["format"] == "json"
    assert "path" in d
    assert os.path.exists(d["path"])


def test_export_csv(client):
    r = client.post("/api/results/export", json={"format": "csv"})
    assert r.status_code == 200
    d = r.get_json()
    assert os.path.exists(d["path"])


def test_export_markdown(client):
    r = client.post("/api/results/export", json={"format": "markdown"})
    assert r.status_code == 200
    d = r.get_json()
    assert os.path.exists(d["path"])
    with open(d["path"], encoding="utf-8") as f:
        md = f.read()
    assert "| # |" in md


def test_export_unsupported_format(client):
    r = client.post("/api/results/export", json={"format": "pdf"})
    assert r.status_code == 400


def test_export_forbidden_headers(client):
    r = client.post("/api/results/export", json={"format": "json"},
                    headers={"Authorization": "Bearer xyz"})
    assert r.status_code == 403


def test_export_no_key_leak(client):
    r = client.post("/api/results/export", json={"format": "json"})
    j = json.dumps(r.get_json())
    assert "sk-" not in j
    assert "Bearer" not in j
