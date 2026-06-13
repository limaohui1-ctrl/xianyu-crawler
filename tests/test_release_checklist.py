"""Tests for release checklist."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.ops.release_checklist import CHECKS, ck

def test_ck_function():
    CHECKS.clear()
    assert ck("test_pass", True, "msg")
    assert not ck("test_fail", False, "err")
    assert len(CHECKS) == 2
    assert CHECKS[0]["status"] == "PASS"
    assert CHECKS[1]["status"] == "FAIL"

def test_checklist_structure():
    CHECKS.clear()
    ck("ACS_MODE=shadow default", os.environ.get("ACS_MODE","shadow")=="shadow")
    ck("ACS_MODE=on not default", os.environ.get("ACS_MODE","shadow")!="on")
    ck("API Key not in source", True)
    ck("Dashboard starts", True)
    assert len(CHECKS) >= 4

def test_checklist_name_uniqueness():
    CHECKS.clear()
    names = ["Adapter", "Self-test", "Pytest", "Health check", "API Key", "Dashboard"]
    for n in names: ck(n, True)
    assert len(CHECKS) == len(names)

def test_checklist_all_pass_status():
    CHECKS.clear()
    for n in range(5): ck(f"check_{n}", True)
    passed = sum(1 for c in CHECKS if c["ok"])
    assert passed == 5
