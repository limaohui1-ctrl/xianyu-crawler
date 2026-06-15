"""Tests for user onboarding docs — verify all required docs exist and are complete."""
import os, sys, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_user_quick_start_exists():
    path = os.path.join(PROJ, "docs", "USER_QUICK_START.md")
    assert os.path.exists(path), f"Missing: {path}"
    content = _read(path)
    assert len(content) > 500, "USER_QUICK_START.md too short"
    # Must mention key concepts
    for keyword in ["Docker Desktop", "SearXNG", ".env", "Excel", "主题"]:
        assert keyword in content, f"USER_QUICK_START.md missing: {keyword}"
    # Must NOT mention legacy xianyu
    assert "闲鱼" not in content, "USER_QUICK_START.md references legacy 咸鱼"


def test_searxng_setup_exists():
    path = os.path.join(PROJ, "docs", "SEARXNG_SETUP.md")
    assert os.path.exists(path), f"Missing: {path}"
    content = _read(path)
    assert len(content) > 500, "SEARXNG_SETUP.md too short"
    for keyword in ["docker compose", "settings.yml", "8080", "json"]:
        assert keyword in content, f"SEARXNG_SETUP.md missing: {keyword}"


def test_troubleshooting_exists():
    path = os.path.join(PROJ, "docs", "TROUBLESHOOTING.md")
    assert os.path.exists(path), f"Missing: {path}"
    content = _read(path)
    assert len(content) > 500, "TROUBLESHOOTING.md too short"
    for keyword in ["Docker", "8080", ".env", "SearXNG"]:
        assert keyword in content, f"TROUBLESHOOTING.md missing: {keyword}"
    # Must NOT mention legacy
    assert "闲鱼" not in content


def test_readme_quick_start():
    path = os.path.join(PROJ, "README.md")
    assert os.path.exists(path)
    content = _read(path)
    # Must have quick start section
    assert "首次安装" in content
    assert "日常使用" in content
    assert "USER_QUICK_START.md" in content
    assert "SEARXNG_SETUP.md" in content
    assert "TROUBLESHOOTING.md" in content


def test_env_example_complete():
    path = os.path.join(PROJ, ".env.example")
    assert os.path.exists(path), "Missing .env.example"
    content = _read(path)
    required_keys = [
        "ACS_MODE",
        "ACS_SEARCH_PROVIDER",
        "ACS_SEARXNG_BASE_URL",
        "ACS_SEARXNG_TIMEOUT",
        "ACS_SEARXNG_SAFESEARCH",
        "ACS_SEARXNG_LANGUAGE",
    ]
    for key in required_keys:
        assert key in content, f".env.example missing: {key}"
    # Must NOT contain real secrets
    assert "sk-" not in content, ".env.example contains API key-like string"


def test_startup_searxng_hint():
    """start_acs_desktop.py should check SearXNG connectivity on startup."""
    path = os.path.join(PROJ, "start_acs_desktop.py")
    assert os.path.exists(path)
    content = _read(path)
    assert "SearXNG" in content, "start_acs_desktop.py missing SearXNG check"
    assert ".env.example" in content, "start_acs_desktop.py missing .env hint"


def test_no_xianyu_in_docs():
    """No documentation should reference legacy xianyu/咸鱼."""
    for root, dirs, files in os.walk(os.path.join(PROJ, "docs")):
        for f in files:
            if f.endswith(".md"):
                path = os.path.join(root, f)
                content = _read(path)
                assert "闲鱼" not in content, f"{os.path.relpath(path, PROJ)} references 咸鱼"
