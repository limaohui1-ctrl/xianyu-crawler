"""Tests for source_discovery (main orchestrator)."""
import sys, os, tempfile, shutil, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.source_discovery import SourceDiscovery


@pytest.fixture
def sd():
    d = tempfile.mkdtemp()
    s = SourceDiscovery(d)
    yield s
    shutil.rmtree(d, ignore_errors=True)


def test_discover_basic(sd):
    r = sd.discover("园区废气治理案例", ["VOCs", "活性炭", "整改报告"])
    assert "report" in r
    assert "candidates" in r
    assert len(r["candidates"]) >= 1
    assert r["report"]["total_candidates"] >= 1


def test_discover_has_all_statuses(sd):
    r = sd.discover("VOCs治理", ["VOCs", "活性炭"], limit=50)
    statuses = [c["compliance_status"] for c in r["candidates"]]
    assert "allowed" in statuses
    assert "blocked" in statuses


def test_discover_auto_select(sd):
    r = sd.discover("治理", ["VOCs"], auto_select_allowed=True)
    selected = [c for c in r["candidates"] if c["selected"]]
    assert len(selected) >= 1
    for s in selected:
        assert s["compliance_status"] == "allowed"


def test_discover_exported_file_exists(sd):
    r = sd.discover("测试", ["VOCs"], auto_select_allowed=True)
    assert os.path.exists(r["selected_urls_path"])
    with open(r["selected_urls_path"]) as f:
        lines = [l.strip() for l in f if l.strip()]
    assert len(lines) >= 1


def test_discover_blocked_not_selected(sd):
    r = sd.discover("amazon filter", ["amazon", "test"], auto_select_allowed=True)
    for c in r["candidates"]:
        if c["compliance_status"] == "blocked":
            assert c["selected"] is False


def test_load_batch(sd):
    r1 = sd.discover("test", ["test"])
    bid = r1["batch_id"]
    r2 = sd.load_batch(bid)
    assert len(r2["candidates"]) == len(r1["candidates"])


def test_load_batch_not_found(sd):
    r = sd.load_batch("nonexistent_batch_12345")
    assert "error" in r


def test_discover_no_api_key(sd):
    r = sd.discover("test", ["VOCs"], auto_select_allowed=True)
    import json
    j = json.dumps(r["candidates"])
    assert "sk-" not in j
    assert "Bearer" not in j
