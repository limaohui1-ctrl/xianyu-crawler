"""Tests for SearchApiQuota."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.search_api_quota import SearchApiQuota

def test_quota_allows_within_limit():
    q = SearchApiQuota(daily_limit=5)
    for i in range(5):
        assert q.check()
        q.record_call(True)
    assert not q.check()

def test_quota_status():
    q = SearchApiQuota(daily_limit=10)
    q.check()          # triggers daily reset
    q.record_call(True)
    q.record_call(False)
    s = q.status()
    assert s["calls_made"] == 2
    assert s["errors"] == 1
    assert s["remaining"] == 8
