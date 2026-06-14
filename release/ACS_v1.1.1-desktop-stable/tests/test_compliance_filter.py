"""Tests for compliance_filter."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.compliance_filter import ComplianceFilter, BLOCKED_DOMAINS
from acs.discovery.candidate_url import CandidateUrl


def test_allowed_gov_domain():
    cf = ComplianceFilter()
    c = cf.evaluate(CandidateUrl(url="https://www.epb.gov.cn/doc", source_domain="epb.gov.cn"))
    assert c.compliance_status == "allowed"
    assert c.risk_level == "low"


def test_blocked_amazon():
    cf = ComplianceFilter()
    c = cf.evaluate(CandidateUrl(url="https://www.amazon.com/dp/B00TEST", source_domain="amazon.com"))
    assert c.compliance_status == "blocked"
    assert c.risk_level == "blocked"
    assert "403" in c.reason or "blocking" in c.reason


def test_blocked_walmart():
    cf = ComplianceFilter()
    c = cf.evaluate(CandidateUrl(url="https://www.walmart.com/item/123", source_domain="walmart.com"))
    assert c.compliance_status == "blocked"


def test_blocked_login():
    cf = ComplianceFilter()
    c = cf.evaluate(CandidateUrl(url="https://example.com/login?return=/doc", source_domain="example.com"))
    assert c.compliance_status == "blocked"


def test_blocked_token_param():
    cf = ComplianceFilter()
    c = cf.evaluate(CandidateUrl(url="https://example.com/doc?token=abc123", source_domain="example.com"))
    assert c.compliance_status == "blocked"


def test_blocked_captcha():
    cf = ComplianceFilter()
    c = cf.evaluate(CandidateUrl(url="https://example.com/captcha", source_domain="example.com"))
    assert c.compliance_status == "blocked"


def test_blocked_paywall():
    cf = ComplianceFilter()
    c = cf.evaluate(CandidateUrl(url="https://news.com/paywall/article", source_domain="news.com"))
    assert c.compliance_status == "blocked"


def test_needs_review_commercial():
    cf = ComplianceFilter()
    c = cf.evaluate(CandidateUrl(url="https://blog.example.com/post", source_domain="example.com"))
    assert c.compliance_status in ("needs_review", "allowed")


def test_filter_all():
    cf = ComplianceFilter()
    candidates = [
        CandidateUrl(url="https://www.amazon.com/x", source_domain="amazon.com"),
        CandidateUrl(url="https://www.epb.gov.cn/y", source_domain="epb.gov.cn"),
        CandidateUrl(url="https://example.com/login", source_domain="example.com"),
    ]
    filtered = cf.filter_all(candidates)
    statuses = [c.compliance_status for c in filtered]
    assert "blocked" in statuses
    assert "allowed" in statuses


def test_all_blocked_domains_known():
    assert "amazon.com" in BLOCKED_DOMAINS
    assert "walmart.com" in BLOCKED_DOMAINS
    assert "homedepot.com" in BLOCKED_DOMAINS
    assert "ebay.com" in BLOCKED_DOMAINS
