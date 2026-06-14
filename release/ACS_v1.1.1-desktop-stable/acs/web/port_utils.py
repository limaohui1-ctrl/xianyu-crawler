"""Port utilities — check if a port is available."""
import socket


def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """Return True if port is available for binding."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return True
    except OSError:
        return False


def find_free_port(start: int = 5020, end: int = 6000) -> int:
    """Find the first free port in a range. Returns port or raises."""
    for port in range(start, end + 1):
        if is_port_available(port):
            return port
    raise RuntimeError(f"No free ports in range {start}-{end}")
