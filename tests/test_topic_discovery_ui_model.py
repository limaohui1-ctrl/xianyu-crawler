"""Tests: UI data model for topic discovery."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.topic_discovery_flow import discover_by_topic, TopicDiscoveryReport

def test_report_has_ui_fields():
    report = discover_by_topic("VOCs", ["活性炭"], provider="mock", limit=5)
    d = {
        "batch_id": report.batch_id,
        "topic": report.topic,
        "keywords": report.keywords,
        "queries_generated": report.queries_generated,
        "raw_results": report.raw_results,
        "after_dedup": report.after_dedup,
        "allowed": report.allowed,
        "blocked": report.blocked,
        "candidates": report.candidates[:5] if report.candidates else [],
    }
    # Verify structure expected by UI
    assert "batch_id" in d
    assert isinstance(d["allowed"], int)
    for c in d["candidates"]:
        assert "url" in c
        assert "title" in c
        assert "content_type" in c
        assert "compliance_status" in c
        assert "source_quality_score" in c
        assert "_total_score" in c

def test_auto_selected():
    report = discover_by_topic("VOCs", ["活性炭"], provider="mock", limit=5)
    for c in report.candidates:
        if c.get("compliance_status") == "allowed":
            assert c.get("selected") is True
