"""Tests for site_entry_discovery."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.site_entry_discovery import SiteEntryDiscovery


def mock_fetch(url):
    if "/news" in url or "/policy" in url:
        return "<html><title>Page</title></html>", 200
    return None, 404


def test_probe_returns_candidates():
    se = SiteEntryDiscovery("example.gov.cn", "https://example.gov.cn", fetch_func=mock_fetch)
    entries = se.probe(max_paths=5)
    assert len(entries) >= 1
    for e in entries:
        assert e["discovery_method"] == "site_entry"
        assert e["source_domain"] == "example.gov.cn"


def test_probe_respects_limit():
    se = SiteEntryDiscovery("example.gov.cn", "https://example.gov.cn", fetch_func=mock_fetch)
    entries = se.probe(max_paths=3)
    assert len(entries) <= 3
