"""Tests for search_api_provider_registry."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.search_api_provider_registry import SearchApiRegistry, get_search_registry

def test_registry_singleton():
    r1 = get_search_registry()
    r2 = get_search_registry()
    assert r1 is r2

def test_is_real_configured_boolean():
    """Returns True if SearXNG or other real API detected, False otherwise. Both OK."""
    reg = SearchApiRegistry()
    result = reg.is_real_configured
    assert isinstance(result, bool)

def test_status_has_providers():
    reg = SearchApiRegistry()
    s = reg.status()
    assert "real_configured" in s
    assert "providers" in s
    assert "searxng" in s["providers"] or "bing" in s["providers"]
    # Check no key leak
    for prov, info in s["providers"].items():
        assert "api_key" not in str(info) or "[REDACTED]" in str(info) or "[NOT SET]" in str(info)

def test_get_client_cached():
    reg = SearchApiRegistry()
    c1 = reg.get_client("none")
    c2 = reg.get_client("none")
    assert c1 is c2
