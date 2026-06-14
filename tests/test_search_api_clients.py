"""Tests for search_api_clients."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.search_api_clients import (
    BingSearchClient, NoopSearchClient, create_search_client,
    _extract_domain,
)
from acs.discovery.search_api_config import SearchApiConfig

def test_extract_domain():
    assert _extract_domain("https://www.epb.gov.cn/doc") == "www.epb.gov.cn"

def test_noop_always_empty():
    c = NoopSearchClient(SearchApiConfig(provider="none"))
    assert not c.available
    assert c.search("test") == []

def test_create_none():
    c = create_search_client("none")
    assert isinstance(c, NoopSearchClient)
    assert not c.available

def test_create_bing_no_key():
    c = create_search_client("bing")
    # Falls back to NoopSearchClient when no key
    assert c.available is False  # No real key configured

def test_bing_parse_response():
    cfg = SearchApiConfig(provider="bing", api_key="test", enabled=True, configured=True)
    bing = BingSearchClient(cfg)
    data = {
        "webPages": {
            "value": [
                {"url": "https://x.com/1", "name": "Title 1", "snippet": "Snippet 1"},
                {"url": "https://x.com/2", "name": "Title 2", "snippet": "Snippet 2"},
            ]
        }
    }
    results = bing._parse_bing_response(data, "test", 10)
    assert len(results) == 2
    assert results[0].title == "Title 1"
    assert results[0].source_domain == "x.com"
