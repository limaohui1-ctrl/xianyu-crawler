"""Tests: SiteEntryDiscovery blocks commercial domains BEFORE network request."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.site_entry_discovery import SiteEntryDiscovery, _is_commercial


def test_is_commercial_amazon():
    assert _is_commercial("amazon.com") is True
    assert _is_commercial("www.amazon.com") is True


def test_is_commercial_walmart():
    assert _is_commercial("walmart.com") is True


def test_is_commercial_not_blocked():
    assert _is_commercial("example.gov.cn") is False
    assert _is_commercial("books.toscrape.com") is False


def test_probe_returns_empty_for_commercial():
    fetch_calls = []
    def track_fetch(url):
        fetch_calls.append(url)
        return None, 404

    se = SiteEntryDiscovery("amazon.com", "https://amazon.com", fetch_func=track_fetch)
    entries = se.probe(max_paths=5)
    assert len(entries) == 0, "Commercial should return zero entries"
    assert se.blocked is True
    assert "amazon.com" in se.block_reason
    assert len(fetch_calls) == 0, "Must not make any network call for commercial domain"


def test_probe_normal_domain_still_works():
    fetch_calls = []
    def mock_fetch(url):
        fetch_calls.append(url)
        if "/news" in url:
            return "<html></html>", 200
        return None, 404

    se = SiteEntryDiscovery("example.gov.cn", "https://example.gov.cn", fetch_func=mock_fetch)
    entries = se.probe(max_paths=5)
    assert se.blocked is False
    assert len(entries) >= 1
    assert len(fetch_calls) >= 1
