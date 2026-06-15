"""Tests that docs cover one-click SearXNG deployment."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(PROJ, rel), encoding="utf-8") as f:
        return f.read()


def test_quick_start_mentions_one_click():
    content = _read("docs/USER_QUICK_START.md")
    assert "启动" in content or "start" in content.lower()


def test_searxng_setup_mentions_docker_compose():
    content = _read("docs/SEARXNG_SETUP.md")
    assert "docker compose" in content.lower()
    assert "settings.yml" in content


def test_troubleshooting_mentions_8080():
    content = _read("docs/TROUBLESHOOTING.md")
    assert "8080" in content


def test_readme_mentions_searxng():
    content = _read("README.md")
    assert "SearXNG" in content
    assert "SEARXNG_SETUP" in content
