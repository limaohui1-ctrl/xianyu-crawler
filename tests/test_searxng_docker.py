"""Tests for SearXNG docker wrapper — commands whitelist only."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.local_search.searxng_docker import (
    _run, docker_version, compose_version, docker_running,
    container_exists, container_running, check_port_8080,
)
from acs.local_search.searxng_status import quick_check


def test_docker_binary_exists():
    """docker --version should return something or not crash."""
    ver = docker_version()
    # Either Docker is installed or it isn't — both are valid outcomes
    assert isinstance(ver, str)


def test_check_port_8080_returns_bool():
    val = check_port_8080()
    assert isinstance(val, bool)


def test_quick_check_fails_gracefully():
    """When SearXNG is down, quick_check returns False without crashing."""
    # Test with a non-existent port
    result = quick_check(base_url="http://127.0.0.1:19999", timeout=1)
    assert result is False


def test_container_exists_safe():
    """container_exists should not crash when Docker is unavailable."""
    val = container_exists("non-existent-container-xyz")
    assert isinstance(val, bool)


def test_container_running_safe():
    val = container_running("non-existent-container-xyz")
    assert isinstance(val, bool)
