"""Tests for discovery_report."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.discovery_report import DiscoveryReport
from acs.discovery.candidate_url import CandidateUrl


def test_create_default():
    r = DiscoveryReport()
    assert r.batch_id
    assert r.created_at


def test_from_candidates():
    candidates = [
        CandidateUrl(url="https://x.com/1", compliance_status="allowed", source_domain="x.com"),
        CandidateUrl(url="https://x.com/2", compliance_status="needs_review", source_domain="x.com"),
        CandidateUrl(url="https://x.com/3", compliance_status="blocked", source_domain="x.com",
                     risk_level="blocked"),
    ]
    r = DiscoveryReport.from_candidates(candidates, topic="test", keywords=["a", "b"])
    assert r.total_candidates == 3
    assert r.allowed_count == 1
    assert r.needs_review_count == 1
    assert r.blocked_count == 1


def test_to_dict():
    r = DiscoveryReport(topic="test", total_candidates=10)
    d = r.to_dict()
    assert d["topic"] == "test"
    assert d["total_candidates"] == 10


def test_summary():
    candidates = [
        CandidateUrl(url="https://x.com/1", compliance_status="allowed", source_domain="x.com",
                     selected=True),
    ]
    r = DiscoveryReport.from_candidates(candidates, topic="测试")
    s = r.summary()
    assert "测试" in s
    assert "1" in s


def test_no_api_key():
    r = DiscoveryReport(topic="k")
    import json
    j = json.dumps(r.to_dict())
    assert "sk-" not in j
    assert "Bearer" not in j
