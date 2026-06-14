"""Tests for TopicQueryPlanner."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.topic_query_planner import TopicQueryPlanner

def test_generates_queries():
    p = TopicQueryPlanner()
    qs = p.plan("园区废气治理", ["VOCs", "活性炭"])
    assert len(qs) >= 3

def test_no_blocked_words():
    p = TopicQueryPlanner()
    qs = p.plan("test", ["爬虫", "bypass"])
    for q in qs:
        assert "爬虫" not in q
        assert "bypass" not in q

def test_content_type_qualifies():
    p = TopicQueryPlanner()
    qs = p.plan("治理", ["VOCs"], content_type="policy")
    has_policy = any("政策" in q or "公告" in q for q in qs)
    assert has_policy

def test_keywords_only():
    p = TopicQueryPlanner()
    qs = p.plan("", ["VOCs", "活性炭"])
    assert len(qs) >= 1

def test_respects_limit():
    p = TopicQueryPlanner()
    qs = p.plan("废气治理案例", ["VOCs","活性炭","整改","排放","监测","管理","控制"], limit=5)
    assert len(qs) <= 5

def test_no_duplicates():
    p = TopicQueryPlanner()
    qs = p.plan("治理", ["VOCs","活性炭"])
    assert len(qs) == len(set(qs))
