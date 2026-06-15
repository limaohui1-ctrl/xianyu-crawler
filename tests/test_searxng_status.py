"""Tests for SearXNG status checker — works without Docker."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.local_search.searxng_status import (
    check_full_status, quick_check,
    OK_DOCKER_READY, WARN_DOCKER_NOT_RUNNING, WARN_DOCKER_NOT_INSTALLED,
    WARN_CONTAINER_NOT_FOUND, WARN_CONTAINER_STOPPED, OK_SEARXNG_READY,
)


def test_check_full_status_returns_dict():
    result = check_full_status()
    assert isinstance(result, dict)
    assert "status" in result
    assert "docker_installed" in result
    assert "docker_running" in result
    assert "hints" in result


def test_status_has_valid_code():
    result = check_full_status()
    valid = {WARN_DOCKER_NOT_INSTALLED, WARN_DOCKER_NOT_RUNNING,
             WARN_CONTAINER_NOT_FOUND, WARN_CONTAINER_STOPPED,
             OK_SEARXNG_READY, OK_DOCKER_READY}
    assert result["status"] in valid or result["status"].startswith("WARN_")


def test_quick_check_unreachable():
    result = quick_check(base_url="http://127.0.0.1:19999", timeout=1)
    assert result is False


def test_status_has_hints_when_not_ready():
    result = check_full_status()
    if "WARN_" in result["status"]:
        assert len(result["hints"]) > 0, "Should have hints when not ready"
