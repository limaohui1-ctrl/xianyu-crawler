"""Tests for metadata_extractor — extract title, author, date, domain from HTML."""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from acs.content.metadata_extractor import extract_metadata


# ── Test data ──

HTML_FULL_OG = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <title>Page Title in Title Tag</title>
    <meta property="og:title" content="OG Title：环保政策最新解读">
    <meta name="description" content="这是一篇关于环保政策的深度解读文章">
    <meta property="og:description" content="OG Description about environmental policy">
    <meta name="author" content="李四">
    <meta name="article:published_time" content="2025-06-01T08:00:00Z">
</head>
<body>
    <h1>H1 Fallback Title</h1>
    <p>Content goes here.</p>
</body>
</html>"""

HTML_WITH_TITLE_ONLY = """<!DOCTYPE html>
<html>
<head><title>Simple Title</title></head>
<body><p>Just text.</p></body>
</html>"""

HTML_WITH_DATE_META = """<!DOCTYPE html>
<html>
<head>
    <title>News Article</title>
    <meta name="pubdate" content="2025/01/15">
    <meta name="author" content="王五">
</head>
<body><p>Article body.</p></body>
</html>"""

HTML_WITH_TIME_ELEMENT = """<!DOCTYPE html>
<html>
<head><title>Time Test</title></head>
<body>
    <time datetime="2025-04-20">April 20, 2025</time>
    <p>Content.</p>
</body>
</html>"""

EMPTY_HTML = ""


# ── Tests ──

def test_extract_metadata_full_og():
    """Full HTML with OG tags should extract all metadata."""
    result = extract_metadata(HTML_FULL_OG, url="https://example.com/article/1")

    # OG title takes priority
    assert result["title"] == "OG Title：环保政策最新解读"
    assert result["author"] == "李四"
    assert result["publish_time"] == "2025-06-01"
    assert result["source_domain"] == "example.com"
    assert result["description"] != ""
    assert result["language"] == "zh-CN"


def test_extract_metadata_pdf_content_type_hint():
    """PDF content_type_hint should return title from URL filename."""
    result = extract_metadata(
        html="",
        url="https://example.com/reports/annual-report-2025.pdf",
        content_type_hint="pdf",
    )

    assert result["title"] == "annual report 2025"
    assert result["source_domain"] == "example.com"
    assert result["error"] == ""


def test_extract_metadata_doc_content_type_hint():
    """DOC content_type_hint should return title from URL."""
    result = extract_metadata(
        html="",
        url="https://docs.example.com/files/policy_draft_v3.docx",
        content_type_hint="docx",
    )

    assert result["title"] == "policy draft v3"
    assert result["source_domain"] == "docs.example.com"


def test_extract_metadata_missing_fields():
    """When HTML has no metadata tags, fields should be empty."""
    result = extract_metadata(EMPTY_HTML, url="https://example.com/empty")

    assert result["title"] == ""
    assert result["author"] == ""
    assert result["publish_time"] == ""
    assert result["source_domain"] == "example.com"
    assert result["error"] == "No HTML to extract metadata from"


def test_extract_metadata_title_from_title_tag():
    """When no OG tags, title should come from <title> tag."""
    result = extract_metadata(HTML_WITH_TITLE_ONLY, url="https://example.com/simple")

    assert result["title"] == "Simple Title"


def test_extract_metadata_date_from_meta():
    """Date should be extracted from meta pubdate and normalized."""
    result = extract_metadata(HTML_WITH_DATE_META, url="https://example.com/news")

    assert result["publish_time"] == "2025-01-15"
    assert result["author"] == "王五"


def test_extract_metadata_date_from_time_element():
    """Date should be extracted from <time> element datetime attribute."""
    result = extract_metadata(HTML_WITH_TIME_ELEMENT, url="https://example.com/time")

    assert result["publish_time"] == "2025-04-20"


def test_extract_metadata_no_url():
    """With no URL, source_domain should be empty."""
    result = extract_metadata(HTML_WITH_TITLE_ONLY, url="")

    assert result["source_domain"] == ""


def test_extract_metadata_description():
    """Description should be extracted from meta tags."""
    result = extract_metadata(HTML_FULL_OG, url="https://example.com/article/1")

    assert "环保政策" in result["description"] or "environmental" in result["description"].lower()
