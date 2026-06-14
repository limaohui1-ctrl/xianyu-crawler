"""Tests for source_discovery — new provider coverage."""
import sys, os, tempfile, shutil, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.source_discovery import SourceDiscovery


@pytest.fixture
def sd():
    d = tempfile.mkdtemp()
    s = SourceDiscovery(d)
    yield s
    shutil.rmtree(d, ignore_errors=True)


def test_discover_mock(sd):
    r = sd.discover("test", ["VOCs"], provider="mock")
    assert len(r["candidates"]) >= 1


def test_discover_import_file(sd):
    import tempfile
    d = tempfile.mkdtemp()
    p = os.path.join(d, "urls.txt")
    with open(p, "w") as f:
        f.write("https://epb.gov.cn/doc1\nhttps://example.com/doc2\n")
    r = sd.discover("test", ["test"], provider="import-file", limit=10,
                    extra_params={"input_path": p})
    assert len(r["candidates"]) == 2
    shutil.rmtree(d, ignore_errors=True)


def test_discover_sitemap(sd, monkeypatch):
    SITEMAP = b"""<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://epb.gov.cn/p1.html</loc></url>
  <url><loc>https://example.com/p2.html</loc></url>
</urlset>"""
    class Fake:
        def read(self): return SITEMAP
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=15: Fake())
    r = sd.discover("test", ["test"], provider="sitemap", limit=10,
                    extra_params={"sitemap_url": "https://x.com/sitemap.xml"})
    assert len(r["candidates"]) >= 1


def test_discover_rss(sd, monkeypatch):
    RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>T1</title><link>https://epb.gov.cn/1</link></item>
    </channel></rss>"""
    class Fake:
        def read(self): return RSS
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=15: Fake())
    r = sd.discover("test", ["test"], provider="rss", limit=10,
                    extra_params={"feed_url": "https://x.com/feed.xml"})
    assert len(r["candidates"]) >= 1


def test_discover_unknown_provider(sd):
    with pytest.raises(ValueError):
        sd.discover("test", [], provider="nonexistent")


def test_discover_empty_input(sd):
    r = sd.discover("test", [], provider="import-file", extra_params={"input_path": ""})
    assert r["candidates"] == []


def test_discover_auto_select(sd):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "urls.txt")
    with open(p, "w") as f:
        f.write("https://epb.gov.cn/doc1\n")
    r = sd.discover("test", [], provider="import-file", auto_select_allowed=True,
                    extra_params={"input_path": p})
    assert r["report"]["selected_count"] >= 1
    shutil.rmtree(d, ignore_errors=True)


def test_discover_no_api_key(sd):
    r = sd.discover("test", ["test"], provider="mock")
    import json
    j = json.dumps(r)
    assert "sk-" not in j
    assert "Bearer" not in j
