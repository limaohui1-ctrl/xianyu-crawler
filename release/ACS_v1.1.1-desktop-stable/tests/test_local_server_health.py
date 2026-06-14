"""Tests for ACS Local Discovery Server."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.web.local_server import app, _security_check


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    d = r.get_json()
    assert d["status"] == "ok"
    assert d["acs_mode"] == "shadow"
    assert d["production_enabled"] is False


def test_health_acs_mode_in_response(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    d = r.get_json()
    assert d["acs_mode"] == "shadow"
    assert d["production_enabled"] is False


def test_discovery_run_mock(client):
    r = client.post("/api/discovery/run", json={
        "provider": "mock", "topic": "VOCs治理",
        "keywords": ["VOCs", "活性炭"], "limit": 10
    })
    assert r.status_code == 200
    d = r.get_json()
    assert d["total_candidates"] >= 1
    assert d["batch_id"]
    assert len(d["candidates"]) >= 1
    for c in d["candidates"]:
        assert "url" in c
        assert "compliance_status" in c


def test_discovery_run_import_file(client):
    import tempfile, shutil
    d = tempfile.mkdtemp()
    p = os.path.join(d, "urls.txt")
    with open(p, "w") as f:
        f.write("https://epb.gov.cn/doc1\nhttps://example.com/doc2\n")
    r = client.post("/api/discovery/run", json={
        "provider": "import-file", "input_path": p, "limit": 10
    })
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_candidates"] >= 1
    shutil.rmtree(d, ignore_errors=True)


def test_discovery_run_missing_input(client):
    r = client.post("/api/discovery/run", json={
        "provider": "import-file", "limit": 10
    })
    assert r.status_code == 400


def test_discovery_run_blocked_provider(client):
    for p in ["search", "google", "bing", "serpapi"]:
        r = client.post("/api/discovery/run", json={"provider": p})
        assert r.status_code == 403


def test_discovery_run_unknown_provider(client):
    r = client.post("/api/discovery/run", json={"provider": "nonexistent"})
    assert r.status_code == 400
