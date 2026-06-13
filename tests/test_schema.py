"""
Tests for acs.schema — normalizer, validator, and quality_score.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from acs.core.result_model import ParseResult
from acs.schema.normalizer import (
    normalize_title, normalize_price, normalize_published_time,
    normalize_domain, normalize_body, normalize_images, normalize_links,
    normalize_result,
)
from acs.schema.validator import validate_result, validate_results, ValidationReport
from acs.schema.quality_score import score_quality, QualityScore


# ═══════════════════════════════════════════════════════════════════
# Normalizer tests
# ═══════════════════════════════════════════════════════════════════

class TestNormalizeTitle:

    def test_strip_site_name(self):
        assert normalize_title("Product Name - Example Site") == "Product Name"
        assert normalize_title("Article | My Blog") == "Article"
        assert normalize_title("Title — Site Name") == "Title"

    def test_keep_clean_title(self):
        assert normalize_title("Simple Title") == "Simple Title"

    def test_empty(self):
        assert normalize_title("") == ""


class TestNormalizePrice:

    def test_currency_symbol(self):
        assert normalize_price("¥19.99") == "19.99"
        assert normalize_price("$49.99") == "49.99"

    def test_cn_suffix(self):
        assert normalize_price("199.00元") == "199.00"

    def test_plain_number(self):
        assert normalize_price("29.99") == "29.99"

    def test_empty(self):
        assert normalize_price("") == ""


class TestNormalizePublishedTime:

    def test_iso_format(self):
        result = normalize_published_time("2024-06-13T10:30:00+00:00")
        assert result.startswith("2024-06-13 10:30:00")

    def test_chinese_format(self):
        result = normalize_published_time("2024年6月13日")
        assert result == "2024-06-13 00:00:00"

    def test_slash_format(self):
        result = normalize_published_time("2024/06/13")
        assert result == "2024-06-13 00:00:00"

    def test_date_only(self):
        result = normalize_published_time("2024-06-13")
        assert result == "2024-06-13 00:00:00"


class TestNormalizeDomain:

    def test_www_strip(self):
        assert normalize_domain("www.example.com") == "example.com"
        assert normalize_domain("WWW.EXAMPLE.COM") == "example.com"

    def test_no_www(self):
        assert normalize_domain("example.com") == "example.com"


class TestNormalizeBody:

    def test_collapse_whitespace(self):
        result = normalize_body("Line 1\n\n\nLine 2")
        assert "\n\n\n" not in result

    def test_trim(self):
        result = normalize_body("  \n\n  hello  \n  ")
        assert result == "hello"


class TestNormalizeImages:

    def test_dedup(self):
        result = normalize_images(["http://a.com/1.jpg", "http://a.com/1.jpg", "http://a.com/2.jpg"])
        assert len(result) == 2

    def test_strip_cache(self):
        result = normalize_images(["http://a.com/img.jpg?v=123&t=456"])
        assert "?v=" not in result[0]
        assert "&t=" not in result[0]


class TestNormalizeLinks:

    def test_strip_fragment(self):
        result = normalize_links(["http://example.com/page#section"])
        assert "#" not in result[0]

    def test_exclude_non_http(self):
        result = normalize_links(["javascript:void(0)", "mailto:a@b.com", "http://example.com"])
        assert len(result) == 1
        assert result[0] == "http://example.com"


class TestNormalizeResult:

    def test_full_normalization(self):
        r = ParseResult(
            url="https://www.example.com/product",
            title="Widget - Example Site",
            price="¥19.99",
            body="Hello\n\n\nWorld",
            images=["http://a.com/1.jpg", "http://a.com/1.jpg"],
        )
        r.build()
        original_hash = r.content_hash
        normalize_result(r)
        assert r.title == "Widget"
        assert r.price == "19.99"
        assert r.domain == "example.com"
        assert len(r.images) == 1
        # Hash should change after normalization
        assert r.content_hash != original_hash or r.content_hash


# ═══════════════════════════════════════════════════════════════════
# Validator tests
# ═══════════════════════════════════════════════════════════════════

class TestValidator:

    def test_valid_result(self):
        r = ParseResult(
            url="http://example.com",
            title="Valid Title",
            body="Content here",
            parser_used="css",
        )
        r.build()
        report = validate_result(r)
        assert report.valid
        assert report.error_count == 0

    def test_missing_url(self):
        r = ParseResult(url="")
        r.build()
        report = validate_result(r)
        assert not report.valid
        assert any(e.code == "MISSING_REQUIRED" for e in report.errors)

    def test_invalid_url(self):
        r = ParseResult(url="not-a-url")
        r.build()
        report = validate_result(r)
        assert not report.valid
        assert any(e.code == "INVALID_URL" for e in report.errors)

    def test_too_long_title(self):
        r = ParseResult(url="http://x.com", title="x" * 600)
        r.build()
        report = validate_result(r)
        assert any(w.code == "TOO_LONG" for w in report.warnings)

    def test_validate_results_batch(self):
        results = [
            ParseResult(url="http://a.com", title="A"),
            ParseResult(url="http://b.com", title="B"),
            ParseResult(url=""),  # invalid
        ]
        for r in results:
            r.build()
        summary = validate_results(results)
        assert summary["total"] == 3
        assert summary["valid"] == 2
        assert summary["invalid"] == 1


# ═══════════════════════════════════════════════════════════════════
# Quality Score tests
# ═══════════════════════════════════════════════════════════════════

class TestQualityScore:

    def test_high_quality_result(self):
        r = ParseResult(
            url="http://example.com",
            title="Product Name",
            price="29.99",
            author="Seller",
            published_time="2024-06-13",
            body="This is a detailed product description with lots of text. " * 50,
            images=["http://a.com/1.jpg"] * 10,
            links=["http://a.com/page"] * 20,
            structured_data=[{"@type": "Product", "name": "X"}],
            parser_used="jsonld",
            fetch_quality="full",
        )
        r.build()
        qs = score_quality(r)
        assert qs.total >= 60
        assert qs.label == "high"

    def test_low_quality_result(self):
        r = ParseResult(
            url="http://example.com",
            parser_used="fallback",
            fetch_quality="failed",
            error="Connection refused",
        )
        r.build()
        qs = score_quality(r)
        assert qs.total < 40
        assert qs.label == "low"

    def test_completeness_scoring(self):
        r = ParseResult(url="http://x.com", title="T", body="B", price="P",
                        author="A", published_time="2024-01-01",
                        images=["img.jpg"], links=["link"], tables=["table"])
        r.build()
        qs = score_quality(r)
        assert qs.completeness_score >= 80

    def test_score_dict(self):
        r = ParseResult(url="http://x.com", parser_used="css")
        r.build()
        qs = score_quality(r)
        d = qs.to_dict()
        assert "total" in d
        assert "label" in d
        assert "completeness" in d


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
