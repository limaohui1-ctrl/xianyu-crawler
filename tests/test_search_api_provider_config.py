"""Tests for SearchApiConfig — key safety."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.search_api_config import get_search_api_config, SearchApiConfig

def test_no_key_configured_by_default():
    cfg = get_search_api_config("bing")
    assert cfg.configured is False
    assert cfg.enabled is False

def test_safe_dict_never_exposes_key():
    cfg = SearchApiConfig(provider="bing", api_key="secret-123", enabled=True, configured=True)
    safe = cfg.to_safe_dict()
    assert "api_key" not in safe
    assert safe["enabled"] is True

def test_to_dict_redacts_key():
    cfg = SearchApiConfig(api_key="sk-real-key")
    d = cfg.to_dict()
    assert d["api_key"] == "[REDACTED]"

def test_unsupported_provider():
    cfg = get_search_api_config("google_custom_unsupported")
    assert cfg.enabled is False
    assert cfg.message
