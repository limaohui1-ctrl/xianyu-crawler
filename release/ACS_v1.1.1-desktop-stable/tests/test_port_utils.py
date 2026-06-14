"""Tests for port_utils."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.web.port_utils import is_port_available, find_free_port


def test_is_port_available_true():
    assert is_port_available(50985) is True


def test_find_free_port():
    port = find_free_port(50980, 50990)
    assert 50980 <= port <= 50990
    assert is_port_available(port)


def test_find_free_port_returns_different_ports():
    """Two successive calls should return different free ports."""
    p1 = find_free_port(50970, 50979)
    p2 = find_free_port(50970, 50979)
    # Both valid
    assert 50970 <= p1 <= 50979
    assert 50970 <= p2 <= 50979
    assert is_port_available(p1)
    assert is_port_available(p2)
