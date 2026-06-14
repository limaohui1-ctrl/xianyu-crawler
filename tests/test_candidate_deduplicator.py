"""Tests for candidate_deduplicator."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.candidate_deduplicator import dedup_candidates

def test_exact_url_dedup():
    cs = [
        {"url": "https://x.com/a?utm=fb", "title": "A report", "source_domain": "x.com"},
        {"url": "https://x.com/a", "title": "A copy", "source_domain": "x.com"},
    ]
    r = dedup_candidates(cs)
    assert len(r) == 1

def test_different_titles_not_duped():
    cs = [
        {"url": "https://x.com/one", "title": "Completely different title alpha", "source_domain": "x.com"},
        {"url": "https://x.com/two", "title": "Totally other topic beta gamma", "source_domain": "x.com"},
    ]
    r = dedup_candidates(cs)
    assert len(r) == 2

def test_domain_cap():
    cs = []
    for i in range(15):
        cs.append({"url": f"https://x.com/p{i}", "title": f"Unique title number {i}", "source_domain": "x.com"})
    r = dedup_candidates(cs, max_per_domain=10)
    assert len(r) <= 10
    for c in cs[10:]:
        assert c.get("is_duplicate") is True
