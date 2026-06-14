"""Tests: shadow task bridge — full flow mock→select→task."""
import sys, os, pytest, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.web.local_server import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_full_flow_mock_to_task(client):
    """Full flow: mock discover → select allowed → create task."""
    # 1. Discover
    r = client.post("/api/discovery/run", json={
        "provider": "mock", "topic": "治理", "keywords": ["VOCs", "活性炭"], "limit": 20
    })
    assert r.status_code == 200
    batch = r.get_json()
    assert batch["total_candidates"] >= 1

    # 2. Select only allowed
    allowed = [c for c in batch["candidates"] if c["compliance_status"] == "allowed"]
    assert len(allowed) >= 1
    r = client.post("/api/discovery/select", json={
        "batch_id": batch["batch_id"],
        "selected_urls": [c["url"] for c in allowed],
    })
    assert r.status_code == 200

    # 3. Create task
    r = client.post("/api/tasks/create-from-selected", json={
        "batch_id": batch["batch_id"],
    })
    assert r.status_code == 200
    task = r.get_json()
    assert task["mode"] == "shadow"
    assert task["acs_mode_on"] is False


def test_import_file_flow(client):
    """Full flow: import-file → select → task."""
    d = tempfile.mkdtemp()
    p = os.path.join(d, "urls.txt")
    with open(p, "w") as f:
        f.write("https://epb.gov.cn/doc1\nhttps://epb.gov.cn/doc2\nhttps://amazon.com/dp/test\n")
    r = client.post("/api/discovery/run", json={
        "provider": "import-file", "input_path": p, "limit": 10
    })
    shutil.rmtree(d, ignore_errors=True)
    assert r.status_code == 200
    batch = r.get_json()
    # Amazon should be blocked
    blocked = [c for c in batch["candidates"] if c["compliance_status"] == "blocked"]
    assert len(blocked) >= 1


def test_selected_urls_file_created(client):
    """Verify selected_urls.txt is created after select."""
    r = client.post("/api/discovery/run", json={
        "provider": "mock", "topic": "治理", "keywords": ["VOCs"], "limit": 20
    })
    batch = r.get_json()
    allowed = [c for c in batch["candidates"] if c["compliance_status"] == "allowed"]
    r = client.post("/api/discovery/select", json={
        "batch_id": batch["batch_id"],
        "selected_urls": [c["url"] for c in allowed[:3]],
    })
    assert r.status_code == 200
    sel = r.get_json()
    assert os.path.exists(sel["selected_urls_path"])
    with open(sel["selected_urls_path"]) as f:
        lines = [l.strip() for l in f if l.strip()]
    assert len(lines) >= 1
