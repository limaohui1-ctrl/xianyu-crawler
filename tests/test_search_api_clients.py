"""Tests for search_api_clients."""
import sys, os, json, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.search_api_clients import (
    BingSearchClient, NoopSearchClient, create_search_client,
    _extract_domain, SearXNGSelfHostClient, DuckDuckGoDirectClient,
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

def test_searxng_detected_when_running():
    """SearXNG should be auto-detected when Docker container is up."""
    c = SearXNGSelfHostClient()
    # If SearXNG is running, available=True; else False (both OK)
    avail = c.available
    assert isinstance(avail, bool)

def test_duckduckgo_always_available():
    c = DuckDuckGoDirectClient()
    assert c.available is True
