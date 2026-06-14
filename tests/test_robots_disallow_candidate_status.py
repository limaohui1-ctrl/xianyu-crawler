"""Tests: robots Disallow paths mark matching candidates as blocked."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.domain_profile import _apply_robots_disallow


def test_disallow_exact_match():
    cands = [
        {"url": "https://example.gov.cn/admin", "compliance_status": "allowed", "risk_level": "low", "reason": ""},
        {"url": "https://example.gov.cn/public", "compliance_status": "allowed", "risk_level": "low", "reason": ""},
    ]
    _apply_robots_disallow(cands, ["/admin"])
    assert cands[0]["compliance_status"] == "blocked"
    assert "Disallow" in cands[0]["reason"]
    assert cands[1]["compliance_status"] == "allowed"


def test_disallow_prefix_match():
    cands = [
        {"url": "https://example.gov.cn/admin/users", "compliance_status": "allowed", "risk_level": "low", "reason": ""},
    ]
    _apply_robots_disallow(cands, ["/admin"])
    assert cands[0]["compliance_status"] == "blocked"


def test_disallow_no_match():
    cands = [
        {"url": "https://example.gov.cn/about", "compliance_status": "allowed", "risk_level": "low", "reason": ""},
    ]
    _apply_robots_disallow(cands, ["/admin"])
    assert cands[0]["compliance_status"] == "allowed"


def test_disallow_empty_list():
    cands = [
        {"url": "https://example.gov.cn/admin", "compliance_status": "allowed", "risk_level": "low", "reason": ""},
    ]
    _apply_robots_disallow(cands, [])
    assert cands[0]["compliance_status"] == "allowed"


def test_disallow_root_path():
    cands = [
        {"url": "https://example.gov.cn/", "compliance_status": "allowed", "risk_level": "low", "reason": ""},
    ]
    _apply_robots_disallow(cands, ["/"])
    assert cands[0]["compliance_status"] == "blocked"
