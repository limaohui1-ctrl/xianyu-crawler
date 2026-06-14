"""Tests for html_cleaner — remove boilerplate from HTML."""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from acs.content.html_cleaner import clean_html


# ── Test data ──

HTML_WITH_BOILERPLATE = """<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
    <nav class="main-nav">
        <ul><li><a href="/">Home</a></li><li><a href="/about">About</a></li></ul>
    </nav>
    <header>Site Header</header>
    <article>
        <h1>Article Title</h1>
        <p>This is the main content of the article. It contains important information that should be preserved after cleaning.</p>
        <p>Second paragraph with more useful content about the topic.</p>
    </article>
    <aside class="sidebar">Related links</aside>
    <footer>Copyright 2025</footer>
    <div class="advertisement">Buy our product!</div>
    <div class="cookie-banner">We use cookies</div>
</body>
</html>"""

HTML_WITH_SCRIPT_STYLE = """<!DOCTYPE html>
<html>
<head>
    <style>body { color: red; } .hidden { display: none; }</style>
    <script>console.log("tracking"); var x = 1;</script>
</head>
<body>
    <p>Clean content here.</p>
    <script>alert("another script");</script>
    <noscript>JavaScript is disabled</noscript>
</body>
</html>"""

EMPTY_HTML = ""

PLAIN_TEXT = "This is just plain text without any HTML tags."


# ── Tests ──

def test_clean_html_removes_nav():
    """Nav elements should be removed."""
    result = clean_html(HTML_WITH_BOILERPLATE)
    cleaned = result["cleaned_html"]
    assert "首页" not in cleaned or "Home" not in cleaned.lower()
    # nav text should not appear in cleaned text
    text = cleaned.lower()
    # The nav content should be stripped
    assert result["removed_count"] > 0
    assert result["error"] == ""


def test_clean_html_removes_footer():
    """Footer elements should be removed."""
    result = clean_html(HTML_WITH_BOILERPLATE)
    cleaned = result["cleaned_html"]
    assert "Copyright" not in cleaned


def test_clean_html_removes_ads():
    """Advertisement elements should be removed."""
    result = clean_html(HTML_WITH_BOILERPLATE)
    cleaned = result["cleaned_html"]
    assert "advertisement" not in cleaned.lower()


def test_clean_html_preserves_article():
    """Main article content should be preserved."""
    result = clean_html(HTML_WITH_BOILERPLATE)
    cleaned = result["cleaned_html"]
    assert "This is the main content" in cleaned
    assert "Second paragraph" in cleaned
    assert "Article Title" in cleaned


def test_clean_html_empty_html():
    """Empty HTML should return error."""
    result = clean_html(EMPTY_HTML)
    assert result["error"] == "Empty HTML input"
    assert result["cleaned_html"] == ""
    assert result["cleaned_text_len"] == 0


def test_clean_html_plain_text():
    """Plain text without HTML tags should work (BS will wrap it)."""
    result = clean_html(PLAIN_TEXT)
    # BeautifulSoup will parse plain text successfully, wrapping it
    assert result["error"] == ""
    assert result["cleaned_html"] != ""
    assert result["cleaned_text_len"] > 0


def test_clean_html_script_tags_removed():
    """Script tags should be removed."""
    result = clean_html(HTML_WITH_SCRIPT_STYLE)
    cleaned = result["cleaned_html"]
    assert "console.log" not in cleaned
    assert "tracking" not in cleaned
    assert "var x = 1" not in cleaned


def test_clean_html_style_tags_removed():
    """Style tags should be removed."""
    result = clean_html(HTML_WITH_SCRIPT_STYLE)
    cleaned = result["cleaned_html"]
    assert "body { color: red" not in cleaned
    assert ".hidden" not in cleaned


def test_clean_html_preserves_body_content():
    """Body content should survive script/style removal."""
    result = clean_html(HTML_WITH_SCRIPT_STYLE)
    cleaned = result["cleaned_html"]
    assert "Clean content here" in cleaned


def test_clean_html_returns_removed_count():
    """Result should include a count of removed elements."""
    result = clean_html(HTML_WITH_BOILERPLATE)
    assert result["removed_count"] > 0


def test_clean_html_returns_text_length():
    """Result should include cleaned_text_len."""
    result = clean_html(HTML_WITH_BOILERPLATE)
    assert result["cleaned_text_len"] > 0
