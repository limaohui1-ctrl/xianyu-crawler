"""Server launcher utilities — port check, health polling."""
import socket
import urllib.request
import time


def check_port(port: int, host: str = "127.0.0.1") -> bool:
    """Return True if port is available (not in use)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.bind((host, port))
            return True
    except OSError:
        return False


def wait_for_health(url: str, timeout: int = 30, interval: float = 1.0) -> bool:
    """Poll the health endpoint until it responds or timeout expires.

    Args:
        url: Health check URL (e.g. http://127.0.0.1:5020/api/health)
        timeout: Max seconds to wait
        interval: Seconds between retries

    Returns:
        True if service responded, False if timeout
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            req = urllib.request.Request(url, method="GET")
            resp = urllib.request.urlopen(req, timeout=5)
            body = resp.read().decode("utf-8")
            if '"status":"ok"' in body or '"status": "ok"' in body:
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def is_service_running(host: str = "127.0.0.1", port: int = 5020) -> bool:
    """Quick check if the ACS local server is reachable."""
    return not check_port(port)
