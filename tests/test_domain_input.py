"""Tests for domain_input."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.domain_input import parse_domain, DomainInput


def test_bare_domain():
    di = parse_domain("example.gov.cn")
    assert di.is_valid
    assert di.domain == "example.gov.cn"
    assert di.root_url == "https://example.gov.cn"


def test_www_subdomain():
    di = parse_domain("www.example.gov.cn")
    assert di.domain == "www.example.gov.cn"
    assert di.root_url == "https://www.example.gov.cn"


def test_full_url():
    di = parse_domain("https://example.gov.cn/news/2024")
    assert di.is_valid
    assert di.domain == "example.gov.cn"


def test_rejects_localhost():
    for h in ["localhost", "127.0.0.1", "0.0.0.0"]:
        di = parse_domain(h)
        assert not di.is_valid, f"should reject {h}"


def test_rejects_private_ip():
    for ip in ["192.168.1.1", "10.0.0.1", "172.16.0.1"]:
        di = parse_domain(ip)
        assert not di.is_valid, f"should reject {ip}"


def test_rejects_blocked_protocols():
    for p in ["javascript:alert(1)", "file:///etc/passwd", "data:text/html,hi"]:
        di = parse_domain(p)
        assert not di.is_valid, f"should reject {p}"


def test_empty_input():
    di = parse_domain("")
    assert not di.is_valid


def test_to_dict():
    di = parse_domain("example.gov.cn")
    d = di.to_dict()
    assert d["domain"] == "example.gov.cn"
    assert d["is_valid"] is True
