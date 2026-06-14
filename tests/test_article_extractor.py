"""Tests for article_extractor — full content extraction pipeline."""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from acs.content.article_extractor import extract_article


# ── Test data ──

NORMAL_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <title>环保政策解读：2025年绿色发展新方向</title>
    <meta name="author" content="张三">
    <meta name="article:published_time" content="2025-03-15">
</head>
<body>
    <nav><a href="/">首页</a><a href="/news">新闻</a></nav>
    <article>
        <h1>环保政策解读：2025年绿色发展新方向</h1>
        <p>近日，国务院发布了一系列关于绿色发展的新政策。这些政策涵盖了能源转型、碳减排、生态保护等多个领域。</p>
        <p>专家表示，2025年将是绿色发展的关键之年。各地方政府需要积极响应中央号召，制定符合本地实际的实施方案。</p>
        <p>在能源转型方面，清洁能源占比将进一步提高。预计到2025年底，非化石能源消费比重将达到20%左右。</p>
        <p>此外，碳交易市场也将进一步扩大覆盖范围，更多行业将被纳入碳交易体系。</p>
    </article>
    <footer>© 2025 环保网 版权所有</footer>
</body>
</html>"""

EMPTY_HTML = ""

PDF_URL = "https://example.com/reports/annual_report_2025.pdf"

HTTP_ERROR_HTML = """<!DOCTYPE html>
<html><body><h1>404 Not Found</h1><p>页面不存在</p></body></html>"""

MINIMAL_HTML = """<html><body><p>这是一段简短的正文内容，包含足够多的字数来通过最低段落长度检查。</p><p>这是第二段内容，同样需要足够长才能被提取出来。</p></body></html>"""


# ── Tests ──

def test_extract_article_normal_html():
    """Normal HTML page should extract title, body, author, date."""
    result = extract_article(html=NORMAL_HTML, url="https://example.com/news/green-policy")

    assert result["status"] == "成功"
    assert result["title"] == "环保政策解读：2025年绿色发展新方向"
    assert "绿色发展" in result["main_text"]
    assert result["author"] == "张三"
    assert result["publish_time"] == "2025-03-15"
    assert result["source_domain"] == "example.com"
    assert result["doc_type"] == "webpage"
    assert result["text_length"] > 100
    assert result["paragraph_count"] >= 3
    assert result["quality_label"] in ("high", "medium")
    assert result["error"] == ""


def test_extract_article_empty_html():
    """Empty HTML should return failure status with appropriate error."""
    result = extract_article(html=EMPTY_HTML, url="https://example.com/page")

    assert result["status"] == "失败"
    assert result["error"] == "No HTML content to extract"
    assert result["main_text"] == ""
    assert result["title"] == ""


def test_extract_article_pdf_url():
    """PDF URL should return pdf doc_type and note about parsing not yet implemented."""
    result = extract_article(html="", url=PDF_URL)

    assert result["doc_type"] == "pdf"
    assert result["status"] == "PDF正文解析待增强"
    assert result["error"] == "PDF full-text parsing not yet implemented"
    assert result["title"] == "annual report 2025"


def test_extract_article_http_error():
    """HTTP error status >= 400 should return failure immediately."""
    result = extract_article(
        html=NORMAL_HTML,
        url="https://example.com/page",
        http_status=404,
    )

    assert result["status"] == "失败"
    assert result["error"] == "HTTP 404"


def test_extract_article_minimal_html():
    """Minimal HTML with just body text should still extract."""
    result = extract_article(html=MINIMAL_HTML, url="https://example.com/minimal")

    assert result["main_text"] != ""
    assert "简短的正文内容" in result["main_text"]
    assert result["text_length"] > 0
    # With short-ish text, quality is at least 'low'
    assert result["quality_label"] in ("low", "medium")


def test_extract_article_http_500_error():
    """HTTP 500 status should return failure."""
    result = extract_article(html=NORMAL_HTML, url="https://example.com/page", http_status=500)
    assert result["status"] == "失败"
    assert "500" in result["error"]


def test_extract_article_doc_type_handling():
    """DOC type URL should return appropriate status for non-parseable document."""
    result = extract_article(
        html="",
        url="https://example.com/documents/report.docx",
    )

    assert result["doc_type"] == "doc"
    assert "文档类型已识别" in result["status"]
    assert result["main_text"] == ""
