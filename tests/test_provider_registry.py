"""Tests for provider_registry."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.provider_registry import ProviderRegistry, get_registry
from acs.discovery.candidate_url import CandidateUrl


def test_register_and_get():
    reg = ProviderRegistry()
    reg.register("test", lambda: [CandidateUrl(url="https://x.com")], "desc")
    assert reg.has("test")
    assert not reg.has("nonexistent")
    assert reg.get("test") is not None


def test_list_providers():
    reg = ProviderRegistry()
    reg.register("a", lambda: [], "A desc")
    reg.register("b", lambda: [], "B desc")
    lst = reg.list_providers()
    assert len(lst) == 2
    assert any(p["name"] == "a" for p in lst)


def test_search():
    reg = ProviderRegistry()
    reg.register("mock", lambda **kw: [CandidateUrl(url="https://x.com")], "mock")
    result = reg.search("mock")
    assert len(result) == 1
    assert result[0].url == "https://x.com"


def test_search_unknown():
    reg = ProviderRegistry()
    with pytest.raises(ValueError, match="Unknown provider"):
        reg.search("nonexistent")


def test_global_registry_singleton():
    reg1 = get_registry()
    reg2 = get_registry()
    assert reg1 is reg2
