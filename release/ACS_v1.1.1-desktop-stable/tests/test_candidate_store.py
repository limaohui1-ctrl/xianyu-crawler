"""Tests for candidate_store."""
import sys, os, tempfile, shutil, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.candidate_store import CandidateStore
from acs.discovery.candidate_url import CandidateUrl


@pytest.fixture
def store():
    d = tempfile.mkdtemp()
    s = CandidateStore(d)
    yield s
    shutil.rmtree(d, ignore_errors=True)


def test_save_and_load(store):
    candidates = [
        CandidateUrl(url="https://x.com/1", title="A", source_domain="x.com"),
        CandidateUrl(url="https://x.com/2", title="B", source_domain="x.com", selected=True),
    ]
    path = store.save(candidates, "test_batch")
    assert os.path.exists(path)
    loaded = store.load("test_batch")
    assert len(loaded) == 2
    assert loaded[0].url == "https://x.com/1"
    assert loaded[1].selected is True


def test_load_nonexistent(store):
    result = store.load("nonexistent")
    assert result == []


def test_export_selected_urls(store):
    candidates = [
        CandidateUrl(url="https://x.com/1", title="A", source_domain="x.com", selected=True),
        CandidateUrl(url="https://x.com/2", title="B", source_domain="x.com", selected=False),
    ]
    out = os.path.join(store.store_dir, "test_selected.txt")
    path = store.export_selected_urls(candidates, out)
    assert os.path.exists(path)
    with open(path) as f:
        lines = [l.strip() for l in f if l.strip()]
    assert len(lines) == 1
    assert lines[0] == "https://x.com/1"


def test_mark_selected(store):
    candidates = [
        CandidateUrl(url="https://x.com/1", title="A", source_domain="x.com"),
        CandidateUrl(url="https://x.com/2", title="B", source_domain="x.com"),
    ]
    store.mark_selected(candidates, ["https://x.com/1"])
    assert candidates[0].selected is True
    assert candidates[1].selected is False


def test_mark_selected_never_marks_blocked(store):
    candidates = [
        CandidateUrl(url="https://amazon.com/x", source_domain="amazon.com",
                     compliance_status="blocked", risk_level="blocked"),
    ]
    store.mark_selected(candidates, ["https://amazon.com/x"])
    assert candidates[0].selected is False


def test_get_by_status(store):
    candidates = [
        CandidateUrl(url="https://x.com/1", compliance_status="allowed", source_domain="x.com"),
        CandidateUrl(url="https://x.com/2", compliance_status="blocked", source_domain="x.com"),
    ]
    assert len(store.get_by_status(candidates, "allowed")) == 1
    assert len(store.get_by_status(candidates, "blocked")) == 1


def test_get_selected(store):
    candidates = [
        CandidateUrl(url="https://x.com/1", selected=True, source_domain="x.com"),
        CandidateUrl(url="https://x.com/2", selected=False, source_domain="x.com"),
    ]
    assert len(store.get_selected(candidates)) == 1
