"""
Tests for acs.storage.dedup — URL and content deduplication.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from acs.storage.dedup import (
    DedupStore, normalize_url_for_dedup, content_dedup_key,
)
from acs.core.result_model import ParseResult


class TestNormalizeUrlForDedup:

    def test_lowercase_scheme_host(self):
        result = normalize_url_for_dedup("HTTPS://EXAMPLE.COM/Page")
        assert result == "https://example.com/Page"

    def test_strip_fragment(self):
        result = normalize_url_for_dedup("https://example.com/page#section")
        assert "#" not in result

    def test_strip_tracking_params(self):
        result = normalize_url_for_dedup(
            "https://example.com/page?utm_source=fb&id=123&utm_medium=cpc"
        )
        assert "utm_source" not in result
        assert "utm_medium" not in result
        assert "id=123" in result

    def test_strip_trailing_slash(self):
        result = normalize_url_for_dedup("https://example.com/page/")
        assert result == "https://example.com/page"

    def test_keep_root_slash(self):
        result = normalize_url_for_dedup("https://example.com/")
        assert result == "https://example.com/"

    def test_sort_query_params(self):
        result = normalize_url_for_dedup("https://example.com/page?b=2&a=1")
        assert result == "https://example.com/page?a=1&b=2"

    def test_strip_fbclid_gclid(self):
        result = normalize_url_for_dedup("https://x.com/?fbclid=abc&gclid=def&id=1")
        assert "fbclid" not in result
        assert "gclid" not in result
        assert "id=1" in result


class TestContentDedupKey:

    def test_same_content_same_key(self):
        r1 = ParseResult(url="http://a.com/page1", title="Same", body="Content", price="10")
        r2 = ParseResult(url="http://b.com/page2", title="Same", body="Content", price="10")
        key1 = content_dedup_key(r1)
        key2 = content_dedup_key(r2)
        assert key1 == key2

    def test_different_content_different_key(self):
        r1 = ParseResult(title="A", body="Content A")
        r2 = ParseResult(title="B", body="Content B")
        assert content_dedup_key(r1) != content_dedup_key(r2)

    def test_metadata_independent(self):
        """Content key should NOT depend on URL or timestamp."""
        r1 = ParseResult(url="http://a.com", title="X", body="Y")
        r2 = ParseResult(url="http://z.com", title="X", body="Y")
        assert content_dedup_key(r1) == content_dedup_key(r2)


class TestDedupStore:

    def test_url_dedup(self):
        store = DedupStore()
        assert not store.is_url_duplicate("https://example.com/page")
        store.mark_url("https://example.com/page")
        assert store.is_url_duplicate("https://example.com/page")
        # Normalized variant should also match
        assert store.is_url_duplicate("https://example.com/page#fragment")
        assert store.is_url_duplicate("HTTPS://EXAMPLE.COM/page")

    def test_url_different_paths(self):
        store = DedupStore()
        store.mark_url("https://example.com/page1")
        assert not store.is_url_duplicate("https://example.com/page2")

    def test_content_dedup(self):
        store = DedupStore()
        r1 = ParseResult(title="Widget", body="Description", price="10")
        r1.build()
        r2 = ParseResult(title="Widget", body="Description", price="10")
        r2.build()

        assert not store.is_content_duplicate(r1)
        store.mark_content(r1)
        assert store.is_content_duplicate(r2)

    def test_content_different(self):
        store = DedupStore()
        r1 = ParseResult(title="A", body="Content A")
        r1.build()
        store.mark_content(r1)

        r2 = ParseResult(title="B", body="Content B")
        r2.build()
        assert not store.is_content_duplicate(r2)

    def test_duplicate_counters(self):
        store = DedupStore()
        store.mark_url_duplicate("http://x.com")
        r = ParseResult()
        r.build()
        store.mark_content_duplicate(r)

        stats = store.stats
        assert stats["url_duplicates_skipped"] == 1
        assert stats["content_duplicates_skipped"] == 1

    def test_clear(self):
        store = DedupStore()
        store.mark_url("https://example.com")
        assert store.is_url_duplicate("https://example.com")
        store.clear()
        assert not store.is_url_duplicate("https://example.com")

    def test_stats(self):
        store = DedupStore()
        stats = store.stats
        assert "urls_seen" in stats
        assert "content_hashes_stored" in stats
        assert stats["ttl_seconds"] > 0

    def test_ttl(self):
        """Test that TTL works (with very short TTL)."""
        store = DedupStore(ttl_seconds=0.01)
        store.mark_url("https://example.com")
        import time
        time.sleep(0.02)
        # Should have expired
        assert not store.is_url_duplicate("https://example.com")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
