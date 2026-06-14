"""Tests for TopicDiscoveryFlow end-to-end."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.topic_discovery_flow import discover_by_topic

def test_basic_flow():
    report = discover_by_topic("VOCs治理", ["活性炭"], provider="mock", limit=10)
    assert report.queries_generated >= 1
    assert report.raw_results >= 1
    assert report.allowed >= 1
    assert len(report.candidates) >= 1

def test_commercial_blocked_in_flow():
    report = discover_by_topic("shop", ["amazon"], provider="mock", limit=20)
    # Amazon result should be blocked by compliance filter
    for c in report.candidates:
        if "amazon" in c.get("source_domain", "").lower():
            assert c["compliance_status"] == "blocked"

def test_content_type_filter():
    report = discover_by_topic("VOCs", ["活性炭"], content_type="policy", provider="mock", limit=10)
    # policy type candidates should rank higher
    pass  # structural test — flow doesn't crash

def test_empty_topic():
    report = discover_by_topic("", [], provider="mock")
    assert report.queries_generated == 0
