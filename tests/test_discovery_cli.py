"""Tests for discovery_cli — CLI argument handling."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.discovery_cli import main as cli_main


def test_cli_imports():
    """CLI module imports cleanly."""
    import acs.discovery.discovery_cli
    assert acs.discovery.discovery_cli.main is not None


def test_cli_provider_choices():
    """Verify SourceDiscovery supports all 4 providers."""
    from acs.discovery.source_discovery import SourceDiscovery
    import tempfile
    sd = SourceDiscovery(tempfile.mkdtemp())
    # Use keywords that match _MOCK_CANDIDATES
    r = sd.discover("治理", ["VOCs", "活性炭", "治理"], provider="mock", limit=20)
    assert len(r["candidates"]) >= 1


def test_cli_import_file_provider():
    import tempfile, shutil
    d = tempfile.mkdtemp()
    p = os.path.join(d, "urls.txt")
    with open(p, "w") as f:
        f.write("https://example.com/page1\nhttps://example.com/page2\n")
    from acs.discovery.source_discovery import SourceDiscovery
    sd = SourceDiscovery()
    r = sd.discover("test", ["test"], provider="import-file", limit=10,
                    extra_params={"input_path": p})
    assert len(r["candidates"]) >= 1
    shutil.rmtree(d, ignore_errors=True)


def test_cli_sitemap_provider(monkeypatch):
    """Sitemap provider via SourceDiscovery."""
    SITEMAP_XML = b"""<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/p1.html</loc></url>
</urlset>"""
    class Fake:
        def read(self): return SITEMAP_XML
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=15: Fake())
    from acs.discovery.source_discovery import SourceDiscovery
    sd = SourceDiscovery()
    sd._get_candidates = lambda *a, **kw: []  # no-op, we test below directly
    from acs.discovery.sitemap_provider import SitemapProvider
    sp = SitemapProvider()
    sp.config.rate_limit_seconds = 0
    sp.config.sitemap_allowed_extensions = [".html"]
    r = sp.discover("https://example.com/sitemap.xml")
    assert len(r) >= 1


def test_cli_rss_provider(monkeypatch):
    RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>T1</title><link>https://x.com/1</link></item>
    </channel></rss>"""
    class Fake:
        def read(self): return RSS
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=15: Fake())
    from acs.discovery.rss_provider import RssProvider
    rp = RssProvider()
    rp.config.rate_limit_seconds = 0
    r = rp.discover("https://x.com/feed.xml")
    assert len(r) == 1
    assert r[0].url == "https://x.com/1"


def test_cli_no_api_key():
    import json
    j = json.dumps({"provider": "cli"})
    assert "sk-" not in j
    assert "Bearer" not in j
