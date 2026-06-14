"""Tests for discovery_config."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.discovery_config import DiscoveryConfig, get_config


def test_default_config():
    cfg = DiscoveryConfig()
    assert cfg.default_limit == 50
    assert cfg.request_timeout == 15
    assert cfg.sitemap_max_urls == 200


def test_custom_config():
    cfg = DiscoveryConfig(default_limit=10, request_timeout=5)
    assert cfg.default_limit == 10
    assert cfg.request_timeout == 5


def test_get_config_singleton():
    c1 = get_config()
    c2 = get_config()
    assert c1 is c2


def test_sitemap_allowed_extensions():
    cfg = DiscoveryConfig()
    assert ".html" in cfg.sitemap_allowed_extensions


def test_no_api_key():
    import json
    cfg = DiscoveryConfig()
    j = json.dumps({"timeout": cfg.request_timeout})
    assert "sk-" not in j
