"""Tests for content_deduplicator — detect and mark duplicate content."""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from acs.content.content_deduplicator import (
    deduplicate,
    filter_duplicates,
    normalize_for_dedup,
    title_similarity,
    text_similarity,
    content_hash,
)


# ── Test data ──

def _make_article(url, title, body, domain="example.com"):
    return {
        "url": url,
        "title": title,
        "main_text": body,
        "source_domain": domain,
    }


ARTICLES_NO_DUPES = [
    _make_article("https://a.com/1", "环保政策深度解读", "Body of article one content here about environmental policy."),
    _make_article("https://b.com/2", "量子计算机取得重大突破", "Body of article two content here about quantum computing breakthroughs."),
    _make_article("https://c.com/3", "足球世界杯决赛结果揭晓", "Body of article three content here about World Cup results."),
]

ARTICLES_URL_DUPE = [
    _make_article("https://a.com/1", "Article One", "Body one."),
    _make_article("https://a.com/1", "Article One", "Body one."),  # same URL
    _make_article("https://c.com/3", "Article Three", "Body three."),
]

ARTICLES_TITLE_DUPE = [
    _make_article("https://a.com/1", "环保政策最新解读2025", "Body about environmental policy and green development."),
    _make_article("https://b.com/2", "环保政策最新解读2025", "Completely different body text here."),
    _make_article("https://c.com/3", "Unrelated Article", "Something else entirely."),
]

ARTICLES_BODY_DUPE = [
    _make_article("https://a.com/1", "Title A", "This is the same body text that appears in both articles." * 5),
    _make_article("https://b.com/2", "Title B Different", "This is the same body text that appears in both articles." * 5),
]

ARTICLES_DOMAIN_OVERREP = [
    _make_article("https://a.com/1", "Article 1", "Body 1", "same-domain.com"),
    _make_article("https://a.com/2", "Article 2", "Body 2", "same-domain.com"),
    _make_article("https://a.com/3", "Article 3", "Body 3", "same-domain.com"),
    _make_article("https://a.com/4", "Article 4", "Body 4", "same-domain.com"),
    _make_article("https://a.com/5", "Article 5", "Body 5", "same-domain.com"),
    _make_article("https://a.com/6", "Article 6", "Body 6", "same-domain.com"),  # 6th — over max
]


# ── Tests: deduplicate ──

def test_deduplicate_no_dupes():
    """No duplicates should mark all as non-duplicate."""
    result = deduplicate(ARTICLES_NO_DUPES)

    assert len(result) == 3
    for article in result:
        assert article["is_duplicate"] is False
        assert article["duplicate_of"] == -1
        assert article["duplicate_reason"] == ""


def test_deduplicate_exact_url_duplicate():
    """Exact URL duplicate should be marked."""
    result = deduplicate(ARTICLES_URL_DUPE)

    assert result[0]["is_duplicate"] is False  # first occurrence
    assert result[1]["is_duplicate"] is True   # duplicate
    assert result[1]["duplicate_of"] == 0
    assert result[1]["duplicate_reason"] == "URL重复"
    assert result[2]["is_duplicate"] is False


def test_deduplicate_same_title():
    """Same title should trigger duplicate marking."""
    result = deduplicate(ARTICLES_TITLE_DUPE)

    assert result[0]["is_duplicate"] is False
    assert result[1]["is_duplicate"] is True
    assert "标题" in result[1]["duplicate_reason"]
    assert result[2]["is_duplicate"] is False


def test_deduplicate_same_body():
    """Same body text should trigger duplicate marking."""
    result = deduplicate(ARTICLES_BODY_DUPE)

    assert result[0]["is_duplicate"] is False
    assert result[1]["is_duplicate"] is True
    assert "正文" in result[1]["duplicate_reason"]


def test_deduplicate_domain_overrepresentation():
    """Domain over-representation should mark extras as duplicates."""
    result = deduplicate(ARTICLES_DOMAIN_OVERREP, domain_max=5)

    # First 5 from same-domain.com should be non-duplicate
    for i in range(5):
        assert result[i]["is_duplicate"] is False, f"Article {i} should not be duplicate"

    # 6th should be marked as duplicate
    assert result[5]["is_duplicate"] is True
    assert "域名" in result[5]["duplicate_reason"] or "same-domain.com" in result[5]["duplicate_reason"]


def test_deduplicate_preserves_input_fields():
    """Deduplication should add fields without removing existing ones."""
    result = deduplicate(ARTICLES_NO_DUPES)

    for article in result:
        assert "url" in article
        assert "title" in article
        assert "main_text" in article
        assert "is_duplicate" in article
        assert "duplicate_of" in article
        assert "duplicate_reason" in article


def test_deduplicate_custom_domain_max():
    """Custom domain_max should change threshold."""
    articles = [
        _make_article("https://a.com/1", "A1", "B1", "dom.com"),
        _make_article("https://a.com/2", "A2", "B2", "dom.com"),
        _make_article("https://a.com/3", "A3", "B3", "dom.com"),
    ]

    # With domain_max=2, the 3rd should be duplicate
    result = deduplicate(articles, domain_max=2)
    assert result[0]["is_duplicate"] is False
    assert result[1]["is_duplicate"] is False
    assert result[2]["is_duplicate"] is True

    # With domain_max=5, all should be non-duplicate
    result2 = deduplicate(articles, domain_max=5)
    for a in result2:
        assert a["is_duplicate"] is False


# ── Tests: filter_duplicates ──

def test_filter_duplicates_empty():
    """Empty list should return empty list."""
    assert filter_duplicates([]) == []


def test_filter_duplicates_all_unique():
    """All unique articles should all be returned after dedup."""
    deduped = deduplicate(ARTICLES_NO_DUPES)
    result = filter_duplicates(deduped)
    assert len(result) == 3


def test_filter_duplicates_with_dupes():
    """Duplicates should be filtered out."""
    articles = deduplicate(ARTICLES_URL_DUPE)
    filtered = filter_duplicates(articles)
    assert len(filtered) == 2


# ── Tests: helper functions ──

def test_normalize_for_dedup():
    """normalize_for_dedup should lowercase, strip, normalize whitespace."""
    result = normalize_for_dedup("  Hello   World! 123  ")
    assert result == "helloworld123"


def test_normalize_for_dedup_cjk():
    """normalize_for_dedup should preserve CJK characters."""
    result = normalize_for_dedup("环保政策 解读")
    assert "环保政策解读" in result


def test_title_similarity_identical():
    """Identical titles should have similarity 1.0."""
    sim = title_similarity("环保政策解读", "环保政策解读")
    assert sim == 1.0


def test_title_similarity_different():
    """Completely different titles should have low similarity."""
    sim = title_similarity("环保政策解读", "abcdefghijklmn")
    assert sim < 0.3


def test_title_similarity_empty():
    """Empty titles should return 0.0."""
    assert title_similarity("", "something") == 0.0
    assert title_similarity("something", "") == 0.0


def test_text_similarity_identical():
    """Identical texts should have high similarity."""
    sim = text_similarity("the quick brown fox jumps over the lazy dog", "the quick brown fox jumps over the lazy dog")
    assert sim > 0.8


def test_text_similarity_different():
    """Different texts should have low similarity."""
    sim = text_similarity("aaaa bbbb cccc dddd", "wwww xxxx yyyy zzzz")
    assert sim < 0.3


def test_content_hash_consistent():
    """Same text should produce same hash."""
    h1 = content_hash("hello world")
    h2 = content_hash("hello world")
    assert h1 == h2


def test_content_hash_different():
    """Different text should produce different hash."""
    h1 = content_hash("hello world")
    h2 = content_hash("goodbye world")
    assert h1 != h2
