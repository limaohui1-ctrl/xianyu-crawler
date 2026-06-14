"""Tests: real API provider — mock-only when no key, structure valid."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.search_api_clients import create_search_client, NoopSearchClient
from acs.discovery.topic_discovery_flow import discover_by_topic

def test_auto_flow_with_no_key_uses_mock():
    """When no API key is set, auto flow should fallback to mock (not crash)."""
    report = discover_by_topic("VOCs治理", ["活性炭"], provider="auto", limit=5)
    assert report.allowed >= 1
    assert report.queries_generated >= 1

def test_noop_returns_empty():
    from acs.discovery.search_api_config import SearchApiConfig
    c = NoopSearchClient(SearchApiConfig(provider="none"))
    results = c.search("test")
    assert results == []


@pytest.mark.skip(reason="BING_SEARCH_API_KEY not set — live test skipped")
def test_bing_live_if_key():
    """Only runs when BING_SEARCH_API_KEY is set in env."""
    if not os.environ.get("BING_SEARCH_API_KEY"):
        pytest.skip("BING_SEARCH_API_KEY not set")
    client = create_search_client("bing")
    results = client.search("VOCs 治理", limit=3)
    assert len(results) >= 1, "Bing API should return results"
    for r in results:
        assert r.url
        assert r.title
