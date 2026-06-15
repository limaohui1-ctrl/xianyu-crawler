"""
searxng_status.py — Full SearXNG health check (Docker + HTTP + JSON).
"""

import json
import urllib.request
import urllib.error
from typing import Optional

# Status codes
OK_DOCKER_READY = "OK_DOCKER_READY"
WARN_DOCKER_NOT_RUNNING = "WARN_DOCKER_NOT_RUNNING"
WARN_DOCKER_NOT_INSTALLED = "WARN_DOCKER_NOT_INSTALLED"
WARN_CONTAINER_NOT_FOUND = "WARN_CONTAINER_NOT_FOUND"
WARN_CONTAINER_STOPPED = "WARN_CONTAINER_STOPPED"
WARN_SEARXNG_HTTP_FAILED = "WARN_SEARXNG_HTTP_FAILED"
WARN_SEARXNG_JSON_DISABLED = "WARN_SEARXNG_JSON_DISABLED"
WARN_PORT_8080_OCCUPIED = "WARN_PORT_8080_OCCUPIED"
OK_SEARXNG_READY = "OK_SEARXNG_READY"


def check_full_status(base_url: str = "http://127.0.0.1:8080",
                      container_name: str = "acs-searxng",
                      timeout: int = 5) -> dict:
    """
    Run a full SearXNG health check.

    Returns:
        dict with all status fields + overall status code.
    """
    from .searxng_docker import (
        docker_version, compose_version, docker_running,
        container_exists, container_running, check_port_8080,
    )

    result = {
        "docker_installed": False,
        "docker_running": False,
        "compose_available": False,
        "container_exists": False,
        "container_running": False,
        "port_8080_free": True,
        "http_ready": False,
        "json_enabled": False,
        "base_url": base_url,
        "status": "",
        "errors": [],
        "hints": [],
    }

    # 1. Docker installed?
    if docker_version():
        result["docker_installed"] = True
    else:
        result["status"] = WARN_DOCKER_NOT_INSTALLED
        result["hints"].append("请安装 Docker Desktop: https://www.docker.com/products/docker-desktop/")
        return result

    # 2. Docker running?
    if docker_running():
        result["docker_running"] = True
    else:
        result["status"] = WARN_DOCKER_NOT_RUNNING
        result["hints"].append("请启动 Docker Desktop，等待右下角鲸鱼图标变绿")
        return result

    # 3. Compose available?
    if compose_version():
        result["compose_available"] = True

    # 4. Container exists?
    if container_exists(container_name):
        result["container_exists"] = True
    else:
        result["status"] = WARN_CONTAINER_NOT_FOUND
        result["hints"].append("容器不存在。运行: python -m acs.local_search.searxng_manager setup && start")
        return result

    # 5. Container running?
    if container_running(container_name):
        result["container_running"] = True
    else:
        result["status"] = WARN_CONTAINER_STOPPED
        result["hints"].append("容器已停止。运行: python -m acs.local_search.searxng_manager start")
        return result

    # 6. Port available?
    result["port_8080_free"] = not check_port_8080()

    # 7. HTTP check
    try:
        test_url = f"{base_url}/search?q=test&format=json"
        req = urllib.request.Request(test_url, headers={"User-Agent": "ACS/1.0"})
        resp = urllib.request.urlopen(req, timeout=timeout)
        if resp.status == 200:
            result["http_ready"] = True
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            if "results" in data:
                result["json_enabled"] = True
                result["status"] = OK_SEARXNG_READY
            else:
                result["status"] = WARN_SEARXNG_JSON_DISABLED
                result["hints"].append("JSON 接口未启用，检查 settings.yml 是否包含 'json'")
        else:
            result["status"] = WARN_SEARXNG_HTTP_FAILED
            result["errors"].append(f"HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        result["status"] = WARN_SEARXNG_HTTP_FAILED
        result["errors"].append(f"HTTP {e.code}")
    except Exception as e:
        result["status"] = WARN_SEARXNG_HTTP_FAILED
        result["errors"].append(str(e)[:200])

    return result


def quick_check(base_url: str = "http://127.0.0.1:8080", timeout: int = 3) -> bool:
    """Quick check: can we reach SearXNG JSON API?"""
    try:
        test_url = f"{base_url}/search?q=test&format=json"
        req = urllib.request.Request(test_url, headers={"User-Agent": "ACS/1.0"})
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.status == 200
    except Exception:
        return False
