"""Tests: full topic discovery flow with real API detection."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.topic_discovery_flow import discover_by_topic
from acs.discovery.search_api_provider_registry import get_search_registry

def test_real_registry_status_in_flow():
    """Verify that when no API key is set, flow gracefully uses mock."""
    report = discover_by_topic("废气治理", ["VOCs"], provider="auto", limit=10)
    # Should not crash, should return candidates from mock
    assert report.queries_generated >= 1
    assert report.allowed >= 1

def test_registry_returns_configured_status():
    reg = get_search_registry()
    s = reg.status()
    assert "real_configured" in s
    assert "active" in s
    # No real key → real_configured should be False
    # (Unless user set BING_SEARCH_API_KEY)

def test_flow_preserves_candidate_structure():
    report = discover_by_topic("VOCs", ["活性炭"], provider="mock", limit=3)
    for c in report.candidates:
        for field in ["url", "title", "snippet", "content_type", "source_quality_score", "compliance_status"]:
            assert field in c, f"Missing field {field}"
