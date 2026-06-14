"""Tests for server_launcher — port check, health polling."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.web.server_launcher import check_port, wait_for_health, is_service_running


def test_check_port_available():
    result = check_port(50999)
    assert result is True


def test_wait_for_health_timeout():
    result = wait_for_health("http://127.0.0.1:50997/api/health", timeout=2, interval=0.5)
    assert result is False


def test_is_service_running_false():
    result = is_service_running(port=50996)
    assert result is False
