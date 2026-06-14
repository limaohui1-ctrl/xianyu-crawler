"""Tests for query_builder."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.query_builder import QueryBuilder


def test_build_basic():
    qb = QueryBuilder()
    queries = qb.build("园区废气治理", ["VOCs", "活性炭"], "webpage")
    assert len(queries) >= 1
    assert any("园区废气治理" in q for q in queries)
    assert any("VOCs" in q for q in queries)
    assert any("活性炭" in q for q in queries)


def test_build_returns_max_10():
    qb = QueryBuilder()
    queries = qb.build("test", ["a", "b", "c", "d", "e", "f", "g", "h"], "webpage")
    assert len(queries) <= 10


def test_build_empty_keywords():
    qb = QueryBuilder()
    queries = qb.build("测试主题", [], "webpage")
    assert len(queries) >= 1
    assert "测试主题" in queries[0]


def test_build_no_bypass_queries():
    qb = QueryBuilder()
    queries = qb.build("test", ["VOCs"], "webpage")
    for q in queries:
        assert "token=" not in q.lower()
        assert "session=" not in q.lower()
        assert "cookie=" not in q.lower()
        assert "bypass" not in q.lower()


def test_build_pdf_source_type():
    qb = QueryBuilder()
    queries = qb.build("test", ["pdf"], "pdf")
    assert any("PDF" in q for q in queries)


def test_build_dedup():
    qb = QueryBuilder()
    queries = qb.build("same", ["same", "same"], "webpage")
    assert len(queries) == len(set(queries))
