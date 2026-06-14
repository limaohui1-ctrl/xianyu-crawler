"""Tests for url_safety_checker."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.url_safety_checker import UrlSafetyChecker


def test_safe_url():
    checker = UrlSafetyChecker()
    ok, reason = checker.check("https://example.com/page.html")
    assert ok


def test_blocked_exe():
    checker = UrlSafetyChecker()
    ok, reason = checker.check("https://example.com/bad.exe")
    assert not ok


def test_blocked_localhost():
    checker = UrlSafetyChecker()
    ok, reason = checker.check("http://localhost/test")
    assert not ok


def test_blocked_private_ip():
    checker = UrlSafetyChecker()
    ok, reason = checker.check("http://192.168.1.1/test")
    assert not ok


def test_invalid_protocol():
    checker = UrlSafetyChecker()
    ok, reason = checker.check("ftp://example.com")
    assert not ok


def test_suspicious_javascript():
    checker = UrlSafetyChecker()
    ok, reason = checker.check("javascript:alert(1)")
    assert not ok


def test_empty():
    checker = UrlSafetyChecker()
    ok, reason = checker.check("")
    assert not ok


def test_filter_safe():
    checker = UrlSafetyChecker()
    safe, unsafe = checker.filter_safe([
        "https://example.com/page1",
        "https://example.com/page2.exe",
        "http://127.0.0.1/admin",
    ])
    assert len(safe) == 1
    assert "example.com/page1" in safe[0]
    assert len(unsafe) == 2
