"""Tests: /api/results/list endpoint."""
import sys, os, json, pytest, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.web.local_server import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_results_list_returns_array(client):
    r = client.get("/api/results/list")
    assert r.status_code == 200
    d = r.get_json()
    assert "rows" in d
    assert isinstance(d["rows"], list)


def test_results_list_limit(client):
    r = client.get("/api/results/list?limit=5")
    d = r.get_json()
    assert len(d["rows"]) <= 5


def test_results_list_rows_structure(client):
    r = client.get("/api/results/list?limit=3")
    d = r.get_json()
    for row in d["rows"]:
        for f in ["url", "title", "status"]:
            assert f in row, f"Missing field: {f}"


def test_results_no_key_leak(client):
    r = client.get("/api/results/list?limit=10")
    j = json.dumps(r.get_json())
    assert "sk-" not in j
    assert "Bearer" not in j
