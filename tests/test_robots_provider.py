"""Tests for robots_provider."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.robots_provider import RobotsProvider


def mock_fetch(url):
    content = (
        "User-agent: *\n"
        "Disallow: /admin\n"
        "Sitemap: https://example.gov.cn/sitemap.xml\n"
        "Sitemap: /sitemap-news.xml\n"
    )
    return content, 200


def test_parse_sitemap_urls():
    rp = RobotsProvider(fetch_func=mock_fetch)
    rp.fetch("https://example.gov.cn")
    assert len(rp.sitemap_urls) == 2
    assert any("sitemap.xml" in s for s in rp.sitemap_urls)
    assert any("sitemap-news.xml" in s for s in rp.sitemap_urls)


def test_parse_disallow():
    rp = RobotsProvider(fetch_func=mock_fetch)
    rp.fetch("https://example.gov.cn")
    assert "/admin" in rp.disallow_paths


def test_to_candidates():
    rp = RobotsProvider(fetch_func=mock_fetch)
    rp.fetch("https://example.gov.cn")
    cands = rp.to_candidates("example.gov.cn")
    assert len(cands) == 2
    for c in cands:
        assert c["discovery_method"] == "robots_sitemap"


def test_fetch_failure():
    def fail(url):
        return None, "timeout"
    rp = RobotsProvider(fetch_func=fail)
    rp.fetch("https://example.gov.cn")
    assert not rp.fetch_success
    assert rp.error == "timeout"
