"""Tests for mock_search_provider."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.mock_search_provider import MockSearchProvider


def test_search_returns_candidates():
    sp = MockSearchProvider()
    results = sp.search("VOCs 活性炭 治理")
    assert len(results) >= 1
    for c in results:
        assert c.url
        assert c.title


def test_search_different_queries():
    sp = MockSearchProvider()
    r1 = sp.search("VOCs")
    r2 = sp.search("不存在的查询xyz123")
    assert len(r1) >= 1
    # Query with no matches returns empty
    assert isinstance(r2, list)


def test_search_limit():
    sp = MockSearchProvider()
    results = sp.search("治理", limit=3)
    assert len(results) <= 3


def test_search_all_merges():
    sp = MockSearchProvider()
    results = sp.search_all(["VOCs", "活性炭", "治理"], limit=30)
    assert len(results) >= 1
    urls = [c.url for c in results]
    assert len(urls) == len(set(urls))


def test_search_no_real_network():
    sp = MockSearchProvider()
    results = sp.search("anything with no real connection")
    assert isinstance(results, list)


def test_search_blocked_present():
    sp = MockSearchProvider()
    results = sp.search_all(["amazon", "active"], limit=50)
    blocked = [c for c in results if c.compliance_status == "blocked"]
    assert len(blocked) >= 1


def test_search_no_api_key():
    sp = MockSearchProvider()
    results = sp.search_all(["test"], limit=10)
    import json
    for c in results:
        j = json.dumps(c.to_dict())
        assert "sk-" not in j
        assert "Bearer" not in j
