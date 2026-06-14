"""Tests for candidate_url data model."""
import sys, os, json, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.candidate_url import CandidateUrl


def test_create_default():
    c = CandidateUrl()
    assert c.url == ""
    assert c.compliance_status == "allowed"
    assert c.risk_level == "low"
    assert not c.selected


def test_create_full():
    c = CandidateUrl(
        url="https://example.com/doc",
        title="Test Doc",
        snippet="A test document",
        source_domain="example.com",
        source_type="pdf",
        matched_keywords=["test", "doc"],
        estimated_relevance=0.85,
        compliance_status="needs_review",
        risk_level="medium",
        reason="needs manual check",
    )
    assert c.url == "https://example.com/doc"
    assert c.source_type == "pdf"
    assert c.estimated_relevance == 0.85
    assert c.compliance_status == "needs_review"
    assert len(c.matched_keywords) == 2


def test_to_dict():
    c = CandidateUrl(url="https://x.com", title="X", source_domain="x.com")
    d = c.to_dict()
    assert d["url"] == "https://x.com"
    assert d["title"] == "X"


def test_from_dict():
    d = {"url": "https://y.com", "title": "Y", "source_domain": "y.com",
         "selected": True, "estimated_relevance": 0.5}
    c = CandidateUrl.from_dict(d)
    assert c.url == "https://y.com"
    assert c.selected is True
    assert c.estimated_relevance == 0.5


def test_to_from_roundtrip():
    c1 = CandidateUrl(url="https://z.com", title="Z", source_domain="z.com",
                      matched_keywords=["a", "b"], estimated_relevance=0.9)
    c2 = CandidateUrl.from_dict(c1.to_dict())
    assert c2.url == c1.url
    assert c2.matched_keywords == ["a", "b"]


def test_no_api_key():
    c = CandidateUrl(url="https://k.com", reason="some reason")
    j = json.dumps(c.to_dict())
    assert "sk-" not in j
    assert "Bearer" not in j
    assert "api_key" not in j
