"""Tests for main_text_extractor — extract main body text from cleaned HTML."""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from acs.content.main_text_extractor import extract_main_text


# ── Test data ──

HTML_MULTI_PARAGRAPH = """<html><body>
<article>
    <h1>测试文章标题</h1>
    <p>这是第一段正文内容，包含了比较详细的信息描述，用于测试正文提取功能。</p>
    <p>第二段内容同样重要，提供了更多关于该主题的深入分析和见解。</p>
    <p>第三段总结全文，给读者一个完整的结论和展望。</p>
    <p>第四段补充了一些额外的数据和参考资料。</p>
</article>
</body></html>"""

EMPTY_HTML = ""

HTML_ALL_LINKS = """<html><body>
<nav>
    <ul>
        <li><a href="/home">首页</a></li>
        <li><a href="/news">新闻中心</a></li>
        <li><a href="/products">产品展示</a></li>
        <li><a href="/about">关于我们</a></li>
        <li><a href="/contact">联系方式</a></li>
        <li><a href="/services">服务项目</a></li>
        <li><a href="/faq">常见问题</a></li>
    </ul>
</nav>
</body></html>"""

HTML_SHORT_FRAGMENTS = """<html><body>
<p>短。</p>
<p>太短了。</p>
<p>也不行。</p>
</body></html>"""


# ── Tests ──

def test_extract_main_text_multiple_paragraphs():
    """HTML with multiple paragraphs should extract all of them."""
    result = extract_main_text(HTML_MULTI_PARAGRAPH)

    assert result["error"] == ""
    assert result["paragraph_count"] >= 3
    assert result["text_length"] > 100
    assert "第一段正文内容" in result["main_text"]
    assert "第二段内容" in result["main_text"]
    assert len(result["paragraphs"]) >= 3
    assert result["summary"] != ""


def test_extract_main_text_empty_html():
    """Empty HTML should return error."""
    result = extract_main_text(EMPTY_HTML)

    assert result["error"] == "Empty HTML — no text to extract"
    assert result["main_text"] == ""
    assert result["paragraph_count"] == 0
    assert result["text_length"] == 0


def test_extract_main_text_all_links():
    """HTML where all text is in links (nav menu) should be mostly filtered out."""
    result = extract_main_text(HTML_ALL_LINKS)

    # The link-heavy nav should either be empty or return minimal text
    # because link text > 70% of total triggers skip
    if result["paragraphs"]:
        # If fallback kicked in, the text should still be short
        assert result["paragraph_count"] <= 7
    else:
        assert result["error"] == "No meaningful text extracted from page"


def test_extract_main_text_short_fragments():
    """HTML with only short fragments below min_paragraph_len should not be included."""
    result = extract_main_text(HTML_SHORT_FRAGMENTS)

    # Short fragments below default min_paragraph_len (25) are skipped
    # Falls back to newline-split, but those are also too short
    assert result["paragraph_count"] == 0 or result["error"] != ""


def test_extract_main_text_summary():
    """Summary should be first 200 characters of main_text."""
    result = extract_main_text(HTML_MULTI_PARAGRAPH)

    main_text = result["main_text"]
    summary = result["summary"]

    if len(main_text) > 200:
        assert summary.endswith("...")
        assert summary[:190] == main_text[:190]
    else:
        assert summary == main_text


def test_extract_main_text_returns_all_fields():
    """Result should contain all expected fields."""
    result = extract_main_text(HTML_MULTI_PARAGRAPH)

    assert "main_text" in result
    assert "summary" in result
    assert "paragraphs" in result
    assert "paragraph_count" in result
    assert "text_length" in result
    assert "error" in result


def test_extract_main_text_custom_min_paragraph_len():
    """Custom min_paragraph_len should affect extraction."""
    result_default = extract_main_text(HTML_SHORT_FRAGMENTS, min_paragraph_len=25)
    result_low = extract_main_text(HTML_SHORT_FRAGMENTS, min_paragraph_len=1)

    # With lower threshold, more text should be extracted
    assert result_low["paragraph_count"] >= result_default["paragraph_count"]
