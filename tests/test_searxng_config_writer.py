"""Tests for SearXNG config writer — does not write to real D:\\ACS_SearXNG."""
import sys, os, pytest, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.local_search.searxng_config_writer import (
    setup_searxng_config, check_existing_config, _generate_secret, _backup_existing,
)


def test_generate_secret():
    s = _generate_secret()
    assert len(s) == 64  # token_hex(32) = 64 hex chars
    assert s.isalnum()


def test_setup_creates_files():
    """setup_searxng_config should create docker-compose.yml and settings.yml."""
    tmp = tempfile.mkdtemp()
    try:
        result = setup_searxng_config(deploy_dir=tmp)
        assert os.path.exists(os.path.join(tmp, "docker-compose.yml"))
        assert os.path.exists(os.path.join(tmp, "searxng", "settings.yml"))
        assert "created docker-compose.yml" in result["actions"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_setup_no_overwrite_by_default():
    """Second call should skip if files exist."""
    tmp = tempfile.mkdtemp()
    try:
        setup_searxng_config(deploy_dir=tmp)
        result2 = setup_searxng_config(deploy_dir=tmp)
        assert "skipped" in " ".join(result2["actions"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_setup_overwrite_backs_up():
    """overwrite=True should create .bak files."""
    tmp = tempfile.mkdtemp()
    try:
        setup_searxng_config(deploy_dir=tmp)
        result = setup_searxng_config(deploy_dir=tmp, overwrite=True)
        assert os.path.exists(os.path.join(tmp, "docker-compose.yml.bak"))
        assert "backed_up" in " ".join(result["actions"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_check_existing_config():
    tmp = tempfile.mkdtemp()
    try:
        setup_searxng_config(deploy_dir=tmp)
        result = check_existing_config(deploy_dir=tmp)
        assert result["docker_compose_exists"]
        assert result["settings_exists"]
        assert result["json_enabled"]
        assert result["port_8080"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_settings_has_json():
    tmp = tempfile.mkdtemp()
    try:
        setup_searxng_config(deploy_dir=tmp)
        with open(os.path.join(tmp, "searxng", "settings.yml"), encoding="utf-8") as f:
            content = f.read()
        assert "json" in content
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_compose_has_8080():
    tmp = tempfile.mkdtemp()
    try:
        setup_searxng_config(deploy_dir=tmp)
        with open(os.path.join(tmp, "docker-compose.yml"), encoding="utf-8") as f:
            content = f.read()
        assert "8080" in content
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_backup_existing():
    tmp = tempfile.mkdtemp()
    try:
        path = os.path.join(tmp, "test.txt")
        with open(path, "w") as f:
            f.write("original")
        assert _backup_existing(path)
        assert os.path.exists(path + ".bak")
        with open(path + ".bak") as f:
            assert f.read() == "original"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_backup_nonexistent():
    assert not _backup_existing("/nonexistent/path/xyz.txt")
