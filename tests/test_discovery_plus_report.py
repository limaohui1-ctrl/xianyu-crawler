"""Tests for discovery_plus_report."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.domain_profile import DomainProfile
from acs.discovery.discovery_plus_report import DiscoveryPlusReport


def test_from_profile():
    p = DomainProfile(
        domain="example.gov.cn",
        root_url="https://example.gov.cn",
        robots_sitemaps=["https://x.com/s.xml"],
        sitemap_urls_discovered=["https://x.com/s.xml"],
        feed_urls_discovered=["https://x.com/rss"],
        site_entries=[{"url": "https://x.com/news"}],
        total_candidates=5,
    )
    r = DiscoveryPlusReport.from_profile(p, batch_id="test_001")
    assert r.domain == "example.gov.cn"
    assert r.total_candidates == 5
    assert r.robots_sitemaps_found == 1
    assert r.sitemaps_found == 1
    assert r.feeds_found == 1
    assert r.site_entries_found == 1
    assert r.batch_id == "test_001"
    assert r.created_at


def test_from_profile_auto_batch_id():
    p = DomainProfile(domain="x.com", root_url="https://x.com", total_candidates=0)
    r = DiscoveryPlusReport.from_profile(p)
    assert r.batch_id.startswith("dp_x.com_")
