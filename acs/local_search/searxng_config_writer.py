"""
searxng_config_writer.py — Generate docker-compose.yml and settings.yml.

Only writes to the designated SearXNG deploy directory (default: D:\\ACS_SearXNG).
Never overwrites existing configs without backing them up first.
"""

import os
import shutil
import secrets

DEFAULT_DEPLOY_DIR = r"D:\ACS_SearXNG"

DOCKER_COMPOSE_TEXT = """services:
  searxng:
    image: docker.io/searxng/searxng:latest
    container_name: acs-searxng
    restart: unless-stopped
    ports:
      - "127.0.0.1:8080:8080"
    volumes:
      - ./searxng:/etc/searxng:rw
    environment:
      - SEARXNG_BASE_URL=http://127.0.0.1:8080/
      - SEARXNG_SECRET=***    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - SETGID
      - SETUID
"""

SETTINGS_TEXT = """use_default_settings: true

general:
  instance_name: "ACS Local SearXNG"

search:
  safe_search: 1
  formats:
    - html
    - json

server:
  secret_key: "***"
  bind_address: "0.0.0.0"
  limiter: false
  image_proxy: false
"""


def _generate_secret() -> str:
    return secrets.token_hex(32)


def _backup_existing(path: str) -> bool:
    if os.path.exists(path):
        bak = path + ".bak"
        shutil.copy2(path, bak)
        return True
    return False


def setup_searxng_config(deploy_dir: str = DEFAULT_DEPLOY_DIR,
                         overwrite: bool = False) -> dict:
    result = {"deploy_dir": deploy_dir, "actions": [], "errors": []}
    try:
        os.makedirs(deploy_dir, exist_ok=True)
        os.makedirs(os.path.join(deploy_dir, "searxng"), exist_ok=True)
    except Exception as e:
        result["errors"].append(f"Failed to create directory: {e}")
        return result

    secret = _generate_secret()

    compose_path = os.path.join(deploy_dir, "docker-compose.yml")
    if os.path.exists(compose_path):
        if overwrite:
            _backup_existing(compose_path)
            result["actions"].append("backed_up docker-compose.yml")
        else:
            result["actions"].append("docker-compose.yml exists — skipped")

    if not os.path.exists(compose_path) or overwrite:
        with open(compose_path, "w", encoding="utf-8") as f:
            f.write(DOCKER_COMPOSE_TEXT.format(secret=secret))
        result["actions"].append("created docker-compose.yml")

    settings_path = os.path.join(deploy_dir, "searxng", "settings.yml")
    if os.path.exists(settings_path):
        if overwrite:
            _backup_existing(settings_path)
            result["actions"].append("backed_up settings.yml")
        else:
            result["actions"].append("settings.yml exists — skipped")
            try:
                with open(settings_path, encoding="utf-8") as f:
                    if "json" not in f.read():
                        result.setdefault("warnings", []).append("settings.yml does not include 'json' in formats")
            except Exception:
                pass

    if not os.path.exists(settings_path) or overwrite:
        with open(settings_path, "w", encoding="utf-8") as f:
            f.write(SETTINGS_TEXT.format(secret=secret))
        result["actions"].append("created settings.yml")

    return result


def check_existing_config(deploy_dir: str = DEFAULT_DEPLOY_DIR) -> dict:
    result = {
        "deploy_dir": deploy_dir,
        "docker_compose_exists": False,
        "settings_exists": False,
        "json_enabled": False,
        "port_8080": False,
        "warnings": [],
    }

    compose_path = os.path.join(deploy_dir, "docker-compose.yml")
    if os.path.exists(compose_path):
        result["docker_compose_exists"] = True
        try:
            with open(compose_path, encoding="utf-8") as f:
                if "8080" in f.read():
                    result["port_8080"] = True
        except Exception:
            pass

    settings_path = os.path.join(deploy_dir, "searxng", "settings.yml")
    if os.path.exists(settings_path):
        result["settings_exists"] = True
        try:
            with open(settings_path, encoding="utf-8") as f:
                if "json" in f.read():
                    result["json_enabled"] = True
                else:
                    result["warnings"].append("settings.yml missing 'json' in formats")
        except Exception:
            pass

    return result
