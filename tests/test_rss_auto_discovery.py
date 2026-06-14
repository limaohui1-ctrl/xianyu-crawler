"""Tests for rss_auto_discovery."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.rss_auto_discovery import RssAutoDiscovery


RSS_XML = '<?xml version="1.0"?><rss version="2.0"><channel><item><title>Post 1</title><link>https://example.gov.cn/news/a</link><description>First post</description></item><item><title>Post 2</title><link>https://example.gov.cn/news/b</link><description>Second post</description></item></channel></rss>'

HOMEPAGE_HTML = '<html><head><link rel="alternate" type="application/rss+xml" href="/feed.xml"></head><body></body></html>'


def mock_fetch(url):
    if "/rss" in url or "feed.xml" in url:
        return RSS_XML, 200
    if url.endswith("/"):
        return HOMEPAGE_HTML, 200
    return None, 404


def test_probe_common_paths():
    rd = RssAutoDiscovery("example.gov.cn", "https://example.gov.cn", fetch_func=mock_fetch)
    rd.probe_common_paths()
    assert len(rd.found_feeds) >= 1


def test_probe_homepage_links():
    rd = RssAutoDiscovery("example.gov.cn", "https://example.gov.cn", fetch_func=mock_fetch)
    rd.probe_homepage_links()
    assert len(rd.found_feeds) >= 1


def test_parse_feeds():
    rd = RssAutoDiscovery("example.gov.cn", "https://example.gov.cn", fetch_func=mock_fetch)
    rd.found_feeds = ["https://example.gov.cn/rss"]
    entries = rd.parse_feeds(limit=10)
    assert len(entries) == 2
    assert entries[0]["discovery_method"] == "rss_auto"
    assert entries[0]["title"] == "Post 1"
