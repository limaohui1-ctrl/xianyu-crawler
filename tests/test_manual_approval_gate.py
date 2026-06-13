"""Tests for manual approval gate."""
import sys, os, tempfile, shutil, pytest, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.evaluation.manual_approval_gate import ApprovalGate, ApprovalRecord

@pytest.fixture
def gate():
    d = tempfile.mkdtemp()
    g = ApprovalGate(db_path=os.path.join(d, "approvals.db"))
    yield g
    shutil.rmtree(d, ignore_errors=True)

def test_submit_pending(gate):
    r = gate.submit("example.com", "admin", "need review")
    assert r.decision == "pending"
    assert r.is_valid() is False

def test_approve(gate):
    r = gate.submit("example.com", "admin")
    assert gate.approve(r.approval_id, "admin", "looks good")
    r2 = gate.get_latest("example.com")
    assert r2.decision == "approved"
    assert r2.is_valid() is True

def test_reject(gate):
    r = gate.submit("example.com")
    assert gate.reject(r.approval_id, "admin", "not ready")
    r2 = gate.get_latest("example.com")
    assert r2.decision == "rejected"
    assert r2.is_valid() is False

def test_revoke(gate):
    r = gate.submit("example.com")
    gate.approve(r.approval_id, "admin")
    assert gate.revoke(r.approval_id)
    r2 = gate.get_latest("example.com")
    assert r2.decision == "revoked"

def test_is_ready_for_canary_false_pending(gate):
    gate.submit("example.com")
    assert gate.is_ready_for_canary("example.com") is False

def test_is_ready_for_canary_true(gate):
    r = gate.submit("example.com", "admin")
    gate.approve(r.approval_id, "admin")
    assert gate.is_ready_for_canary("example.com") is True

def test_approval_record_no_api_key():
    r = ApprovalRecord(approval_id="x", site_id="k", reviewer="admin")
    j = json.dumps(r.to_dict())
    assert "sk-" not in j
    assert "Bearer" not in j
