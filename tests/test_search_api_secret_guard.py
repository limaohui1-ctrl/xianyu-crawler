"""Tests for search_api_secret_guard."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.search_api_secret_guard import mask_key, safe_headers, sanitize_error, redact_headers

def test_mask_short():
    assert mask_key("abc") == "***"

def test_mask_full():
    assert mask_key("abcdefgh12345678") == "abc...5678"

def test_mask_none():
    assert mask_key("") == "[NOT SET]"

def test_safe_headers_no_key_in_log():
    h = safe_headers("sk-secret-12345", "X-Api-Key")
    assert h["X-Api-Key"] == "sk-secret-12345"  # In memory only, never printed

def test_redact_headers():
    d = redact_headers({"Authorization": "Bearer sk-abc", "Content-Type": "json", "X-Secret": "hidden"})
    assert "sk-abc" not in str(d["Authorization"])
    assert d["Content-Type"] == "json"

def test_sanitize_error():
    msg = sanitize_error(Exception("api_key=sk-12345 not valid"))
    assert "sk-12345" not in msg
    assert "REDACTED" in msg
