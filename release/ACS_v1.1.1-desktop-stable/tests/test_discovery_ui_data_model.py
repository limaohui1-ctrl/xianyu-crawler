"""Tests: safety checks cover sitemap URLs, RSS links, import-file URLs."""
import sys, os, tempfile, shutil, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_url_safety_blocks_dangerous_sitemap_urls():
    from acs.discovery.url_safety_checker import UrlSafetyChecker
    from acs.discovery.candidate_url import CandidateUrl
    checker = UrlSafetyChecker()
    # Sitemap URLs that contain dangerous patterns
    urls = [
        "https://example.com/page.html",           # safe
        "https://example.com/download.exe",         # dangerous
        "http://192.168.1.1/internal",              # private IP
        "https://example.com/login?return=/doc",    # login pattern (handled by ComplianceFilter)
        "javascript:void(0)",                       # js protocol
        "https://gov.cn/report.pdf",                # safe
    ]
    safe, unsafe = checker.filter_safe(urls)
    assert "https://example.com/page.html" in safe
    assert "https://gov.cn/report.pdf" in safe
    assert "https://example.com/download.exe" not in safe
    assert "http://192.168.1.1/internal" not in safe


def test_rss_links_pass_safety(monkeypatch):
    """RSS provider links go through safety in SourceDiscovery pipeline."""
    RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>Good</title><link>https://epb.gov.cn/article1</link></item>
    </channel></rss>"""
    class Fake:
        def read(self): return RSS
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=15: Fake())
    from acs.discovery.source_discovery import SourceDiscovery
    import tempfile
    sd = SourceDiscovery(tempfile.mkdtemp())
    r = sd.discover("test", ["test"], provider="rss", limit=10,
                    extra_params={"feed_url": "https://x.com/feed.xml"})
    assert len(r["candidates"]) >= 1


def test_sitemap_index_urls_pass_safety(monkeypatch):
    """Sitemap URLs (including from index) go through safety in pipeline."""
    SM = b"""<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://epb.gov.cn/page1.html</loc></url>
  <url><loc>https://example.com/page2.exe</loc></url>
</urlset>"""
    class Fake:
        def read(self): return SM
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=15: Fake())
    from acs.discovery.source_discovery import SourceDiscovery
    import tempfile
    sd = SourceDiscovery(tempfile.mkdtemp())
    r = sd.discover("test", ["test"], provider="sitemap", limit=10,
                    extra_params={"sitemap_url": "https://x.com/sitemap.xml"})
    # .exe URLs should be filtered by safety checker
    urls = [c["url"] for c in r["candidates"]]
    for u in urls:
        assert ".exe" not in u.lower()


def test_import_file_urls_pass_safety():
    """Import-file URLs go through safety+compliance in pipeline."""
    from acs.discovery.source_discovery import SourceDiscovery
    import tempfile
    d = tempfile.mkdtemp()
    p = os.path.join(d, "urls.txt")
    with open(p, "w") as f:
        f.write("https://epb.gov.cn/doc1\n")
        f.write("https://amazon.com/dp/test\n")  # should be blocked by compliance
        f.write("https://example.com/download.exe\n")  # should be blocked by safety
    sd = SourceDiscovery(d)
    r = sd.discover("test", ["test"], provider="import-file", limit=10,
                    extra_params={"input_path": p})
    # blocked items should have compliance_status="blocked"
    blocked = [c for c in r["candidates"] if c["compliance_status"] == "blocked"]
    assert len(blocked) >= 1
    # .exe URLs should not appear at all (filtered by UrlSafetyChecker)
    for c in r["candidates"]:
        assert ".exe" not in c["url"].lower()
    shutil.rmtree(d, ignore_errors=True)


def test_blocked_items_not_in_selected_urls():
    """Blocked candidates are never auto-selected."""
    from acs.discovery.source_discovery import SourceDiscovery
    import tempfile
    d = tempfile.mkdtemp()
    p = os.path.join(d, "urls.txt")
    with open(p, "w") as f:
        f.write("https://epb.gov.cn/doc1\n")
        f.write("https://amazon.com/dp/test\n")
    sd = SourceDiscovery(d)
    r = sd.discover("test", ["test"], provider="import-file", auto_select_allowed=True,
                    extra_params={"input_path": p})
    for c in r["candidates"]:
        if c["compliance_status"] == "blocked":
            assert c["selected"] is False
    shutil.rmtree(d, ignore_errors=True)


def test_selected_urls_export_skips_blocked():
    """selected_urls.txt only contains non-blocked, selected URLs."""
    from acs.discovery.source_discovery import SourceDiscovery
    import tempfile
    d = tempfile.mkdtemp()
    p = os.path.join(d, "urls.txt")
    with open(p, "w") as f:
        f.write("https://epb.gov.cn/doc1\n")
        f.write("https://amazon.com/dp/test\n")
    sd = SourceDiscovery(d)
    r = sd.discover("test", ["test"], provider="import-file", auto_select_allowed=True,
                    extra_params={"input_path": p})
    # Read selected_urls.txt
    if os.path.exists(r["selected_urls_path"]):
        with open(r["selected_urls_path"]) as f:
            urls = [l.strip() for l in f if l.strip()]
        for u in urls:
            assert "amazon.com" not in u.lower()
    shutil.rmtree(d, ignore_errors=True)
