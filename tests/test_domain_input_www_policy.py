"""Tests: www normalization — domain and root_url stay consistent (KEEP www)."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.domain_input import parse_domain


def test_www_kept_in_domain():
    di = parse_domain("www.example.gov.cn")
    assert di.is_valid
    assert di.domain == "www.example.gov.cn", "www must be kept in domain"
    assert di.root_url == "https://www.example.gov.cn"


def test_www_kept_in_root_url():
    di = parse_domain("https://www.example.gov.cn/news")
    assert di.domain == "www.example.gov.cn"
    assert di.root_url == "https://www.example.gov.cn"


def test_no_www_stays_no_www():
    di = parse_domain("example.gov.cn")
    assert di.domain == "example.gov.cn"
    assert di.root_url == "https://example.gov.cn"


def test_domain_root_consistent():
    """domain and root_url must use the same host."""
    for inp in ["www.foo.com", "foo.com", "https://www.bar.org/path"]:
        di = parse_domain(inp)
        assert di.is_valid
        assert di.root_url.endswith(di.domain), f"{inp}: root={di.root_url} domain={di.domain}"


def test_rejection_logic_unaffected():
    # Private IPs still rejected
    assert not parse_domain("127.0.0.1").is_valid
    assert not parse_domain("192.168.0.1").is_valid
    assert not parse_domain("localhost").is_valid
