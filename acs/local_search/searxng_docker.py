"""
searxng_docker.py — Docker CLI wrappers for SearXNG management.

All commands use fixed whitelists — no shell string concatenation from user input.
"""

import subprocess
import os
from typing import Optional

# Whitelist — prevents arbitrary command injection
DOCKER_BINARY = "docker"
COMPOSE_BINARY = "docker"


def _run(cmd: list, timeout: int = 15) -> tuple[int, str, str]:
    """Run a command safely, return (exit_code, stdout, stderr)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError:
        return -1, "", "docker not found"
    except subprocess.TimeoutExpired:
        return -2, "", "timeout"
    except Exception as e:
        return -3, "", str(e)


def docker_version() -> str:
    """Check if docker is installed."""
    rc, out, _ = _run([DOCKER_BINARY, "--version"])
    return out if rc == 0 else ""


def compose_version() -> str:
    """Check if docker compose is available."""
    rc, out, _ = _run([COMPOSE_BINARY, "compose", "version"])
    return out if rc == 0 else ""


def docker_running() -> bool:
    """Check if docker daemon is running."""
    rc, _, _ = _run([DOCKER_BINARY, "info"], timeout=10)
    return rc == 0


def container_exists(name: str = "acs-searxng") -> bool:
    """Check if container exists (any state)."""
    rc, out, _ = _run([DOCKER_BINARY, "ps", "-a", "--filter", f"name={name}", "--format", "{{.Names}}"])
    return rc == 0 and name in out


def container_running(name: str = "acs-searxng") -> bool:
    """Check if container is running."""
    rc, out, _ = _run([DOCKER_BINARY, "ps", "--filter", f"name={name}", "--format", "{{.Status}}"])
    return rc == 0 and "Up" in out


def container_status(name: str = "acs-searxng") -> str:
    """Get container status string or empty if not found."""
    rc, out, _ = _run([DOCKER_BINARY, "ps", "-a", "--filter", f"name={name}", "--format", "{{.Status}}"])
    return out.strip() if rc == 0 and out.strip() else ""


def compose_up(workdir: str, timeout: int = 120) -> tuple[int, str, str]:
    """Run docker compose up -d."""
    return _run([COMPOSE_BINARY, "compose", "up", "-d"], timeout=timeout)


def compose_restart(workdir: str, timeout: int = 60) -> tuple[int, str, str]:
    """Run docker restart on the container."""
    return _run([DOCKER_BINARY, "restart", "acs-searxng"], timeout=timeout)


def compose_pull(workdir: str, timeout: int = 300) -> tuple[int, str, str]:
    """Run docker compose pull."""
    return _run([COMPOSE_BINARY, "compose", "pull"], timeout=timeout)


def compose_down(workdir: str, timeout: int = 30) -> tuple[int, str, str]:
    """Run docker compose down."""
    return _run([COMPOSE_BINARY, "compose", "down"], timeout=timeout)


def check_port_8080() -> bool:
    """Check if port 8080 is already in use (by any process)."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.settimeout(1)
        s.connect(("127.0.0.1", 8080))
        s.close()
        return True
    except Exception:
        return False
