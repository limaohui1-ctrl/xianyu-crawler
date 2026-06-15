"""
searxng_manager.py — Orchestrate SearXNG setup / start / status / restart.

CLI:
    python -m acs.local_search.searxng_manager setup
    python -m acs.local_search.searxng_manager start
    python -m acs.local_search.searxng_manager status
    python -m acs.local_search.searxng_manager restart
"""

import sys
import time
import json

from .searxng_config_writer import setup_searxng_config, check_existing_config, DEFAULT_DEPLOY_DIR
from .searxng_status import check_full_status, quick_check, OK_SEARXNG_READY
from .searxng_docker import (
    docker_version, compose_version, docker_running,
    container_exists, container_running, container_status,
    compose_up, compose_restart, compose_pull, compose_down,
    check_port_8080,
)


def cmd_setup(deploy_dir: str = DEFAULT_DEPLOY_DIR, overwrite: bool = False) -> dict:
    """Run setup: create config files if missing."""
    # Check existing
    existing = check_existing_config(deploy_dir)

    if existing["docker_compose_exists"] and existing["settings_exists"] and not overwrite:
        return {
            "action": "setup",
            "status": "already_configured",
            "deploy_dir": deploy_dir,
            "existing": existing,
        }

    result = setup_searxng_config(deploy_dir, overwrite=overwrite)
    return {
        "action": "setup",
        "status": "configured",
        "deploy_dir": deploy_dir,
        "details": result,
    }


def cmd_start(deploy_dir: str = DEFAULT_DEPLOY_DIR, wait_timeout: int = 60) -> dict:
    """Start SearXNG container and wait for readiness."""
    result = {
        "action": "start",
        "status": "",
        "deploy_dir": deploy_dir,
        "steps": [],
        "errors": [],
    }

    # Pre-flight checks
    if not docker_version():
        result["status"] = "docker_not_installed"
        result["errors"].append("Docker not installed")
        return result

    if not docker_running():
        result["status"] = "docker_not_running"
        result["errors"].append("Docker Desktop is not running")
        return result

    if not check_existing_config(deploy_dir)["docker_compose_exists"]:
        # Auto-setup
        result["steps"].append("auto-setup: creating config files")
        setup_searxng_config(deploy_dir)

    # Pull latest (non-blocking if already pulled)
    rc, out, err = compose_pull(deploy_dir, timeout=60)
    if rc not in (0,):
        result["steps"].append(f"pull warning: {err[:100]}" if err else "pull completed")

    # Start
    rc, out, err = compose_up(deploy_dir)
    result["steps"].append(f"compose_up: exit={rc}")

    if rc != 0:
        result["status"] = "compose_failed"
        result["errors"].append(err[:500])
        return result

    # Wait for readiness
    deadline = time.time() + wait_timeout
    while time.time() < deadline:
        if quick_check():
            result["status"] = "started"
            result["steps"].append("searxng JSON API ready")
            return result
        time.sleep(2)

    result["status"] = "started_no_json"
    result["errors"].append(f"SearXNG started but JSON API not responding within {wait_timeout}s")
    return result


def cmd_status() -> dict:
    """Get full SearXNG status."""
    return check_full_status()


def cmd_restart(wait_timeout: int = 60) -> dict:
    """Restart SearXNG container."""
    result = {"action": "restart", "status": "", "steps": []}

    if not docker_running():
        result["status"] = "docker_not_running"
        return result

    if not container_running():
        result["status"] = "container_not_running"
        result["steps"].append("container was not running — starting instead")
        return cmd_start(wait_timeout=wait_timeout)

    rc, out, err = compose_restart(DEFAULT_DEPLOY_DIR)
    result["steps"].append(f"restart: exit={rc}")

    # Wait for readiness
    deadline = time.time() + wait_timeout
    while time.time() < deadline:
        if quick_check():
            result["status"] = "restarted"
            result["steps"].append("searxng JSON API ready")
            return result
        time.sleep(2)

    result["status"] = "restarted_no_json"
    return result


# ── CLI ──
if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "status"

    if action == "setup":
        out = cmd_setup()
    elif action == "start":
        out = cmd_start()
    elif action == "status":
        out = cmd_status()
    elif action == "restart":
        out = cmd_restart()
    else:
        print(f"Unknown action: {action}")
        print("Usage: python -m acs.local_search.searxng_manager [setup|start|status|restart]")
        sys.exit(1)

    print(json.dumps(out, ensure_ascii=False, indent=2))
