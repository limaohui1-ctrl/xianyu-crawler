"""Tests for url_normalizer."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.url_normalizer import normalize_url, dedup_urls


def test_remove_fragment():
    assert normalize_url("https://x.com/path#anchor") == "https://x.com/path"


def test_remove_utm():
    r = normalize_url("https://x.com/p?utm_source=fb&id=1")
    assert "utm_source" not in r
    assert "id=1" in r


def test_remove_fbclid():
    r = normalize_url("https://x.com/p?fbclid=abc&q=1")
    assert "fbclid" not in r
    assert "q=1" in r


def test_lowercase_domain():
    assert normalize_url("https://EXAMPLE.COM") == "https://example.com/"


def test_normalize_trailing_slash():
    assert normalize_url("https://x.com/path/") == "https://x.com/path"


def test_dedup_removes_duplicates():
    cs = [
        {"url": "https://x.com/a?utm_source=fb", "title": "A"},
        {"url": "https://x.com/a", "title": "A2"},
        {"url": "https://x.com/b", "title": "B"},
    ]
    result = dedup_urls(cs)
    assert len(result) == 2


def test_empty_url():
    assert normalize_url("") == ""
