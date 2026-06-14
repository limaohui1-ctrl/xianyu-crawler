"""Tests for sitemap_auto_discovery."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.sitemap_auto_discovery import SitemapAutoDiscovery


def sitemap_xml(urls):
    items = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    return f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>'


def mock_fetch(url):
    if "sitemap.xml" in url:
        return sitemap_xml([
            "https://example.gov.cn/doc1",
            "https://example.gov.cn/doc2",
        ]), 200
    if "sitemap-other.xml" in url:
        return sitemap_xml(["https://example.gov.cn/doc3"]), 200
    return None, 404


def test_probe_common_paths():
    sd = SitemapAutoDiscovery("example.gov.cn", "https://example.gov.cn", fetch_func=mock_fetch)
    sd.probe_common_paths()
    assert len(sd.found_sitemaps) >= 1


def test_parse_sitemaps():
    sd = SitemapAutoDiscovery("example.gov.cn", "https://example.gov.cn", fetch_func=mock_fetch)
    sd.found_sitemaps = ["https://example.gov.cn/sitemap.xml"]
    cands = sd.parse_sitemaps(limit=10)
    assert len(cands) == 2
    assert cands[0]["discovery_method"] == "sitemap_auto"


def test_add_from_robots():
    sd = SitemapAutoDiscovery("example.gov.cn", "https://example.gov.cn", fetch_func=mock_fetch)
    sd.add_from_robots(["https://example.gov.cn/sitemap-other.xml"])
    cands = sd.parse_sitemaps(limit=10)
    assert len(cands) == 1
