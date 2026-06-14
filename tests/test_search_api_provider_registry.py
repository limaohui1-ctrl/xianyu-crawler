"""Tests for search_api_provider_registry."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.search_api_provider_registry import SearchApiRegistry, get_search_registry

def test_registry_singleton():
    r1 = get_search_registry()
    r2 = get_search_registry()
    assert r1 is r2

def test_real_not_configured_by_default():
    reg = SearchApiRegistry()
    assert not reg.is_real_configured

def test_status_has_providers():
    reg = SearchApiRegistry()
    s = reg.status()
    assert s["real_configured"] is False
    assert "providers" in s
    assert "bing" in s["providers"]
    assert "api_key" not in str(s["providers"]["bing"])  # no key leak

def test_get_client_cached():
    reg = SearchApiRegistry()
    c1 = reg.get_client("none")
    c2 = reg.get_client("none")
    assert c1 is c2
