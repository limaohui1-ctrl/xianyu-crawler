"""Tests for ContentTypeDetector."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.content_type_detector import detect_content_type, classify_candidates

def test_pdf_by_extension():
    assert detect_content_type("https://x.com/doc.pdf") == "pdf"

def test_policy_by_domain():
    assert detect_content_type("https://www.mee.gov.cn/zhengce/123") == "policy"

def test_news_by_snippet():
    assert detect_content_type("https://x.com/a", "新闻标题", "今天发布") == "news"

def test_webpage_default():
    assert detect_content_type("https://x.com/page") == "webpage"

def test_classify_candidates_adds_field():
    cs = [{"url": "https://x.com/doc.pdf"}, {"url": "https://www.mee.gov.cn/zhengce"}]
    classify_candidates(cs)
    assert cs[0]["content_type"] == "pdf"
    assert cs[1]["content_type"] == "policy"
