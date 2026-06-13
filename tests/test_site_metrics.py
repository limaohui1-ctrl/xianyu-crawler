"""Tests for site metrics."""
import sys, os, tempfile, shutil, pytest, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.sites.site_metrics import SiteMetrics

@pytest.fixture
def metrics():
    d = tempfile.mkdtemp()
    log_path = os.path.join(d, "shadow.jsonl")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"url": "https://a.com/p1", "acs_success": True, "acs_completeness": 50}) + "\n")
        f.write(json.dumps({"url": "https://a.com/p2", "acs_success": False, "acs_completeness": 0}) + "\n")
        f.write(json.dumps({"url": "https://b.com/p1", "acs_success": True, "acs_completeness": 80}) + "\n")
    m = SiteMetrics(shadow_log=log_path)
    yield m
    shutil.rmtree(d, ignore_errors=True)

def test_get_entries(metrics):
    entries = metrics.get_all_entries()
    assert len(entries) == 3

def test_site_summary(metrics):
    s = metrics.site_summary("a.com")
    assert s["total"] == 2
    assert s["success_rate"] == 0.5
    assert 24 < s["avg_completeness"] < 26

def test_site_summary_empty(metrics):
    s = metrics.site_summary("nonexistent.com")
    assert s["total"] == 0
    assert s["success_rate"] == 0

def test_all_summaries(metrics):
    summaries = metrics.all_summaries()
    assert len(summaries) >= 1
