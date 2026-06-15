"""Tests for SearXNG manager CLI commands."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.local_search.searxng_manager import cmd_setup, cmd_status


def test_cmd_status_returns_valid():
    result = cmd_status()
    assert isinstance(result, dict)
    assert "status" in result
    assert "docker_installed" in result


def test_cmd_setup_returns_valid():
    import tempfile, shutil
    tmp = tempfile.mkdtemp()
    try:
        result = cmd_setup(deploy_dir=tmp)
        assert "status" in result
        assert "action" in result
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_cmd_setup_skips_existing():
    import tempfile, shutil
    tmp = tempfile.mkdtemp()
    try:
        cmd_setup(deploy_dir=tmp)  # first call creates
        result = cmd_setup(deploy_dir=tmp)  # second call skips
        assert result["status"] == "already_configured"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
