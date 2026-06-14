"""
Tests for acs.parser — all parsers and the parser engine.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from acs.core.result_model import ParseResult
from acs.fetcher.response_classifier import ContentType
from acs.parser.parser_engine import ParserEngine, BaseParser
from acs.parser.css_parser import CssParser
from acs.parser.fallback_parser import FallbackParser
from acs.parser.json_parser import JsonParser
from acs.parser.jsonld_parser import JsonLdParser


# ── Test HTML ───────────────────────────────────────────────────

BASIC_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Test Article</title>
    <meta name="author" content="John Doe">
    <meta name="description" content="A test article about testing">
    <meta property="og:title" content="Test Article - OG">
    <meta property="article:published_time" content="2024-06-13T10:30:00Z">
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "Article",
        "name": "Structured Test Article",
        "headline": "Structured Headline",
        "author": {"name": "Jane Smith"},
        "datePublished": "2024-06-13",
        "description": "Structured description text here.",
        "image": "https://example.com/hero.jpg"
    }
    </script>
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Test Widget",
        "price": "29.99",
        "offers": {"price": "24.99", "priceCurrency": "USD"}
    }
    </script>
</head>
<body>
    <article>
        <h1>Test Article H1</h1>
        <p class="author">By John Doe</p>
        <time datetime="2024-06-13T10:30:00">June 13, 2024</time>
        <div class="content">
            <p>This is the first paragraph of the article body.</p>
            <p>This is the second paragraph with more content.</p>
        </div>
        <img src="https://example.com/img1.jpg" alt="Image 1">
        <img src="https://example.com/img2.jpg" alt="Image 2">
        <a href="/page2">Next Page</a>
        <a href="https://external.com/link">External</a>
        <table>
            <caption>Product Specs</caption>
            <thead><tr><th>Feature</th><th>Value</th></tr></thead>
            <tbody>
                <tr><td>Size</td><td>Large</td></tr>
                <tr><td>Color</td><td>Red</td></tr>
            </tbody>
        </table>
    </article>
</body>
</html>"""

PRICE_HTML = """<!DOCTYPE html>
<html><body>
<div class="product-price">¥ 199.00</div>
<span class="price">$49.99</span>
</body></html>"""

EMPTY_HTML = "<html><body></body></html>"

JSON_API = """{
    "data": {
        "title": "API Product",
        "price": 39.99,
        "description": "This is from an API response.",
        "author": "API Author",
        "created_at": "2024-01-15",
        "image": "https://api.example.com/img.jpg"
    }
}"""


# ═══════════════════════════════════════════════════════════════════
# CSS Parser
# ═══════════════════════════════════════════════════════════════════

class TestCssParser:

    def test_can_handle_html(self):
        p = CssParser()
        assert p.can_handle(ContentType.HTML, BASIC_HTML)
        assert not p.can_handle(ContentType.JSON, BASIC_HTML)

    def test_parse_title(self):
        p = CssParser()
        result = p.parse("http://example.com", BASIC_HTML)
        assert result.title
        # h1 should be "Test Article H1"
        assert "Test Article" in result.title

    def test_parse_body(self):
        p = CssParser()
        result = p.parse("http://example.com", BASIC_HTML)
        assert "first paragraph" in result.body
        assert "second paragraph" in result.body

    def test_parse_images(self):
        p = CssParser()
        result = p.parse("http://example.com", BASIC_HTML)
        assert len(result.images) >= 2
        assert any("img1" in img for img in result.images)
        assert any("img2" in img for img in result.images)

    def test_parse_links(self):
        p = CssParser()
        result = p.parse("http://example.com", BASIC_HTML)
        assert len(result.links) >= 2
        assert any("page2" in link for link in result.links)

    def test_parse_tables(self):
        p = CssParser()
        result = p.parse("http://example.com", BASIC_HTML)
        assert len(result.page_tables) >= 1
        table = result.page_tables[0]
        assert table.caption == "Product Specs"
        assert len(table.rows) >= 2

    def test_parse_price(self):
        p = CssParser()
        result = p.parse("http://example.com", PRICE_HTML)
        assert result.price
        assert "199" in result.price or "49" in result.price

    def test_parse_empty(self):
        p = CssParser()
        result = p.parse("http://example.com", EMPTY_HTML)
        assert result.parser_used == "css"
        assert not result.title

    def test_result_build(self):
        p = CssParser()
        result = p.parse("http://example.com", BASIC_HTML)
        assert result.content_hash
        assert 0 <= result.completeness <= 100
        assert result.domain == "example.com"


# ═══════════════════════════════════════════════════════════════════
# JSON-LD Parser
# ═══════════════════════════════════════════════════════════════════

class TestJsonLdParser:

    def test_can_handle(self):
        p = JsonLdParser()
        assert p.can_handle(ContentType.HTML, BASIC_HTML)
        assert p.can_handle(ContentType.JSON, '{"@type":"Product"}')

    def test_parse_title(self):
        p = JsonLdParser()
        result = p.parse("http://example.com", BASIC_HTML)
        # Should extract "Structured Test Article" or "Test Widget" (first non-empty)
        assert result.title
        assert "Article" in result.title or "Widget" in result.title

    def test_parse_price(self):
        p = JsonLdParser()
        result = p.parse("http://example.com", BASIC_HTML)
        assert result.price
        assert "29" in result.price or "24" in result.price

    def test_parse_author(self):
        p = JsonLdParser()
        result = p.parse("http://example.com", BASIC_HTML)
        assert result.author

    def test_parse_time(self):
        p = JsonLdParser()
        result = p.parse("http://example.com", BASIC_HTML)
        assert result.published_time

    def test_parse_images(self):
        p = JsonLdParser()
        result = p.parse("http://example.com", BASIC_HTML)
        assert len(result.images) >= 1
        assert any("hero" in img for img in result.images)

    def test_parse_no_jsonld(self):
        p = JsonLdParser()
        result = p.parse("http://example.com", EMPTY_HTML)
        assert result.error
        assert result.error_category == "parse_empty"


# ═══════════════════════════════════════════════════════════════════
# JSON Parser
# ═══════════════════════════════════════════════════════════════════

class TestJsonParser:

    def test_can_handle(self):
        p = JsonParser()
        assert p.can_handle(ContentType.JSON, JSON_API)
        assert not p.can_handle(ContentType.HTML, BASIC_HTML)

    def test_parse_title(self):
        p = JsonParser()
        result = p.parse("http://api.example.com", JSON_API)
        assert result.title == "API Product"

    def test_parse_price(self):
        p = JsonParser()
        result = p.parse("http://api.example.com", JSON_API)
        assert "39" in result.price

    def test_parse_body(self):
        p = JsonParser()
        result = p.parse("http://api.example.com", JSON_API)
        assert "API response" in result.body

    def test_parse_author(self):
        p = JsonParser()
        result = p.parse("http://api.example.com", JSON_API)
        assert result.author == "API Author"

    def test_parse_time(self):
        p = JsonParser()
        result = p.parse("http://api.example.com", JSON_API)
        assert result.published_time == "2024-01-15"

    def test_parse_images(self):
        p = JsonParser()
        result = p.parse("http://api.example.com", JSON_API)
        assert len(result.images) >= 1

    def test_parse_invalid_json(self):
        p = JsonParser()
        result = p.parse("http://x.com", "not valid json{{{")
        assert result.error
        assert result.error_category == "parse_invalid_json"


# ═══════════════════════════════════════════════════════════════════
# Fallback Parser
# ═══════════════════════════════════════════════════════════════════

class TestFallbackParser:

    def test_can_handle_anything(self):
        p = FallbackParser()
        assert p.can_handle(ContentType.HTML, BASIC_HTML)
        assert p.can_handle(ContentType.JSON, JSON_API)
        assert p.can_handle(ContentType.PLAIN_TEXT, "hello world")
        assert p.can_handle(ContentType.UNKNOWN, b"\x00\x01".decode("latin-1"))

    def test_parse_title(self):
        p = FallbackParser()
        result = p.parse("http://example.com", BASIC_HTML)
        assert result.title
        assert "Test Article" in result.title or "Test Article H1" in result.title

    def test_parse_images(self):
        p = FallbackParser()
        result = p.parse("http://example.com", BASIC_HTML)
        assert len(result.images) >= 2

    def test_parse_links(self):
        p = FallbackParser()
        result = p.parse("http://example.com", BASIC_HTML)
        assert len(result.links) >= 2

    def test_parse_empty(self):
        p = FallbackParser()
        result = p.parse("http://example.com", "")
        assert result.error
        assert result.error_category == "content_empty"

    def test_parse_body_has_content(self):
        p = FallbackParser()
        result = p.parse("http://example.com", BASIC_HTML)
        assert len(result.body) > 0


# ═══════════════════════════════════════════════════════════════════
# Parser Engine
# ═══════════════════════════════════════════════════════════════════

class TestParserEngine:

    def test_register_and_order(self):
        engine = ParserEngine()
        engine.register(CssParser())
        engine.register(FallbackParser())
        assert "css" in engine.registered_parsers
        assert "fallback" in engine.registered_parsers

    def test_auto_select_best_parser(self):
        engine = ParserEngine()
        engine.register(CssParser())
        engine.register(JsonLdParser())
        engine.register(FallbackParser())

        result, attempts = engine.parse(
            "http://example.com", BASIC_HTML, 200, "text/html"
        )
        assert result is not None
        assert result.parser_used in ("css", "jsonld", "fallback")
        # At least one parser tried
        assert len(attempts) >= 1

    def test_fallback_always_works(self):
        engine = ParserEngine()
        engine.register(FallbackParser())

        result, attempts = engine.parse(
            "http://example.com", "Just some random text, not HTML at all."
        )
        assert result.parser_used == "fallback"
        assert len(attempts) == 1
        assert attempts[0].success

    def test_force_parser(self):
        engine = ParserEngine()
        engine.register(CssParser())
        engine.register(JsonLdParser())

        result, attempts = engine.parse(
            "http://example.com", BASIC_HTML,
            force_parser="css"
        )
        assert result.parser_used == "css"

    def test_unparseable_skipped(self):
        engine = ParserEngine()
        engine.register(FallbackParser())

        result, attempts = engine.parse(
            "http://example.com",
            "<html><body>Please complete the captcha<div class='g-recaptcha'></div></body></html>",
            200, "text/html"
        )
        # Captcha page should be skipped
        assert result.parser_used == "none"
        assert result.error


# ═══════════════════════════════════════════════════════════════════
# Custom Parser (integration test)
# ═══════════════════════════════════════════════════════════════════

class _TestCustomParser(BaseParser):
    name = "test_custom"

    def can_handle(self, content_type: ContentType, body: str) -> bool:
        return "CUSTOM_TRIGGER" in body

    def parse(self, url: str, body: str, **kwargs) -> ParseResult:
        result = ParseResult(url=url, parser_used="test_custom", title="Custom!", body=body)
        result.build()
        return result


class TestCustomParser:

    def test_custom_parser_registration(self):
        engine = ParserEngine()
        engine.register(_TestCustomParser())
        engine.register(FallbackParser())
        # Custom parser must be tried BEFORE fallback
        engine.set_order(["test_custom", "fallback"])

        # Body with CUSTOM_TRIGGER should use the custom parser
        result, attempts = engine.parse(
            "http://example.com", "CUSTOM_TRIGGER content here"
        )
        assert result.parser_used == "test_custom"
        assert result.title == "Custom!"

        # Body without trigger should fall through
        result2, _ = engine.parse(
            "http://example.com", "Ordinary content"
        )
        assert result2.parser_used == "fallback"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
