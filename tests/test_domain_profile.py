"""Tests for domain_profile orchestrator."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.domain_profile import discover_domain, DomainProfile


def robots_xml(urls="https://example.gov.cn/sitemap.xml"):
    return f"Sitemap: {urls}\nDisallow: /admin\n"


def sitemap_xml(urls):
    items = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    return f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>'


def mock_fetch(url):
    if "robots.txt" in url:
        return robots_xml(), 200
    if "sitemap.xml" in url:
        return sitemap_xml(["https://example.gov.cn/doc1", "https://example.gov.cn/doc2"]), 200
    if "/news" in url:
        return "<html></html>", 200
    if "/rss" in url:
        return '<?xml version="1.0"?><rss version="2.0"><channel><item><title>T</title><link>https://example.gov.cn/a</link><description>D</description></item></channel></rss>', 200
    return None, 404


def test_full_discovery():
    profile = discover_domain("example.gov.cn", fetch_func=mock_fetch, max_candidates=20)
    assert profile.domain == "example.gov.cn"
    assert profile.total_candidates >= 1
    assert len(profile.robots_sitemaps) >= 1


def test_discovery_invalid_domain():
    profile = discover_domain("localhost")
    assert not profile.domain or profile.error


def test_discovery_with_flags_disabled():
    profile = discover_domain("example.gov.cn", fetch_func=mock_fetch,
                              enable_robots=False, enable_sitemap=False,
                              enable_rss=False, enable_site_entry=False)
    assert profile.total_candidates == 0
