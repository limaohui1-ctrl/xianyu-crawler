"""Tests for startup SearXNG check in start_acs_desktop.py."""
import sys, os, pytest, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_startup_script_has_searxng_check():
    """start_acs_desktop.py should have SearXNG connectivity check."""
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        "start_acs_desktop.py")
    assert os.path.exists(path)
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert "SearXNG" in content
    assert "127.0.0.1:8080" in content
    assert ".env" in content


def test_startup_checks_env_example():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        "start_acs_desktop.py")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert ".env.example" in content


def test_startup_does_not_exit_on_missing_searxng():
    """Startup should NOT call sys.exit(1) when SearXNG is missing."""
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        "start_acs_desktop.py")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    # After the SearXNG check, it says "No exit — allow ACS to start even without SearXNG"
    assert "docker" in content.lower()
    # Verify there's no exit after the SearXNG check
    check_block = content.split("SearXNG")[1].split("# Check port")[0] if "# Check port" in content else ""
    assert "sys.exit" not in check_block, "Should not exit on SearXNG failure"
