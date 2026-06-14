"""Tests for rss_provider — RSS/Atom feed parsing."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.rss_provider import RssProvider


RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Test Blog</title>
  <item><title>Post 1</title><link>https://example.com/post1</link><description>First post</description></item>
  <item><title>Post 2</title><link>https://example.com/post2</link><description>Second post</description></item>
</channel></rss>"""

ATOM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><title>Atom 1</title><link href="https://example.com/atom1"/><summary>Summary 1</summary></entry>
  <entry><title>Atom 2</title><link href="https://example.com/atom2"/><summary>Summary 2</summary></entry>
</feed>"""


def test_parse_rss(monkeypatch):
    class FakeResponse:
        def read(self): return RSS_XML.encode()
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=15: FakeResponse())
    rp = RssProvider()
    rp.config.rate_limit_seconds = 0
    result = rp.discover("https://example.com/feed.xml")
    assert len(result) == 2
    assert result[0].url == "https://example.com/post1"
    assert result[0].title == "Post 1"
    assert result[0].discovery_method == "rss"


def test_parse_atom(monkeypatch):
    class FakeResponse:
        def read(self): return ATOM_XML.encode()
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=15: FakeResponse())
    rp = RssProvider()
    rp.config.rate_limit_seconds = 0
    result = rp.discover("https://example.com/atom.xml")
    assert len(result) == 2
    assert result[0].title == "Atom 1"
    assert result[0].discovery_method == "rss"


def test_max_entries(monkeypatch):
    class FakeResponse:
        def read(self): return RSS_XML.encode()
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=15: FakeResponse())
    rp = RssProvider()
    rp.config.rate_limit_seconds = 0
    result = rp.discover("https://example.com/feed.xml", max_entries=1)
    assert len(result) == 1


def test_strip_html():
    rp = RssProvider()
    s = rp._strip_html("<p>Hello <b>world</b></p>")
    assert "Hello world" in s


def test_no_api_key():
    import json
    j = json.dumps({"provider": "rss"})
    assert "sk-" not in j
