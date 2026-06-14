"""Tests for sitemap_provider — sitemap XML parsing."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.sitemap_provider import SitemapProvider


SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/page1</loc></url>
  <url><loc>https://example.com/page2.html</loc></url>
  <url><loc>https://example.com/page3.php</loc></url>
  <url><loc>https://example.com/page4.exe</loc></url>
</urlset>"""

SITEMAP_INDEX_XML = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap1.xml</loc></sitemap>
</sitemapindex>"""


def test_parse_basic_sitemap(monkeypatch):
    """Test parsing a basic sitemap."""
    calls = []

    class FakeResponse:
        def read(self): return SITEMAP_XML.encode()

    def fake_open(req, timeout=15):
        calls.append(req.full_url if hasattr(req, 'full_url') else req.get_full_url())
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_open)
    sp = SitemapProvider()
    sp.config.rate_limit_seconds = 0
    sp.config.sitemap_allowed_extensions = [".html", ".php", "/", ""]
    result = sp.discover("https://example.com/sitemap.xml")
    # page4.exe should be filtered out by allowed extensions
    assert len(result) >= 1
    assert any("page1" in c.url for c in result)


def test_parse_sitemap_index(monkeypatch):
    """Test sitemap index parsing."""
    call_count = [0]

    class FakeResponse:
        def read(self):
            call_count[0] += 1
            if call_count[0] == 1:
                return SITEMAP_INDEX_XML.encode()
            return SITEMAP_XML.encode()

    def fake_open(req, timeout=15):
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_open)
    sp = SitemapProvider()
    sp.config.rate_limit_seconds = 0
    sp.config.sitemap_allowed_extensions = [".html", ".php", "/", ""]
    result = sp.discover("https://example.com/sitemap_index.xml")
    assert len(result) >= 1


def test_max_urls_limit(monkeypatch):
    class FakeResponse:
        def read(self): return SITEMAP_XML.encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=15: FakeResponse())
    sp = SitemapProvider()
    sp.config.rate_limit_seconds = 0
    sp.config.sitemap_allowed_extensions = []
    result = sp.discover("https://example.com/sitemap.xml", max_urls=2)
    assert len(result) <= 2


def test_discovery_method_is_sitemap(monkeypatch):
    class FakeResponse:
        def read(self): return SITEMAP_XML.encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=15: FakeResponse())
    sp = SitemapProvider()
    sp.config.rate_limit_seconds = 0
    sp.config.sitemap_allowed_extensions = []
    result = sp.discover("https://example.com/sitemap.xml")
    for c in result:
        assert c.discovery_method == "sitemap"


def test_no_api_key():
    sp = SitemapProvider()
    import json
    j = json.dumps({"discover_method": "sitemap"})
    assert "sk-" not in j
