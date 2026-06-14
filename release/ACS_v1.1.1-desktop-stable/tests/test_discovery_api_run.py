"""Tests: discovery API /run endpoint — all providers."""
import sys, os, pytest, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.web.local_server import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_run_mock_returns_expected_fields(client):
    r = client.post("/api/discovery/run", json={"provider": "mock", "topic": "测试", "keywords": ["VOCs"], "limit": 10})
    assert r.status_code == 200
    d = r.get_json()
    for f in ["batch_id", "total_candidates", "allowed_count", "blocked_count", "candidates", "query"]:
        assert f in d, f"Missing field: {f}"


def test_run_without_json(client):
    r = client.post("/api/discovery/run")
    assert r.status_code == 200  # defaults to mock


def test_run_import_file_with_path(client):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "urls.txt")
    with open(p, "w") as f:
        f.write("https://epb.gov.cn/doc1\n")
    r = client.post("/api/discovery/run", json={"provider": "import-file", "input_path": p, "limit": 5})
    shutil.rmtree(d, ignore_errors=True)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_candidates"] >= 1


def test_run_sitemap_no_url(client):
    r = client.post("/api/discovery/run", json={"provider": "sitemap"})
    assert r.status_code == 400


def test_run_rss_no_url(client):
    r = client.post("/api/discovery/run", json={"provider": "rss"})
    assert r.status_code == 400


def test_run_no_key_in_response(client):
    r = client.post("/api/discovery/run", json={"provider": "mock", "topic": "k", "keywords": ["test"], "limit": 3})
    import json as j
    assert "sk-" not in j.dumps(r.get_json())
