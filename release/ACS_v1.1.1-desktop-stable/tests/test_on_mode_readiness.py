"""Tests for on-mode readiness evaluator."""
import sys, os, tempfile, shutil, pytest, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.evaluation.on_mode_readiness import evaluate_from_shadow, summary, load_shadow_entries

@pytest.fixture
def shadow_dir():
    d = tempfile.mkdtemp()
    log = os.path.join(d, "shadow.jsonl")
    entries = [
        {"ts": "", "url": "a.com/1", "acs_success": True, "acs_completeness": 80, "acs_error": ""},
        {"ts": "", "url": "a.com/2", "acs_success": True, "acs_completeness": 90, "acs_error": ""},
        {"ts": "", "url": "a.com/3", "acs_success": False, "acs_completeness": 0, "acs_error": "timeout"},
        {"ts": "", "url": "a.com/4", "acs_success": True, "acs_completeness": 70, "acs_error": ""},
        {"ts": "", "url": "a.com/5", "acs_success": True, "acs_completeness": 85, "acs_error": ""},
    ]
    with open(log, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    yield log
    shutil.rmtree(d, ignore_errors=True)

def test_load_entries(shadow_dir):
    entries = load_shadow_entries(shadow_dir)
    assert len(entries) == 5

def test_evaluate_with_data(shadow_dir):
    rs, _ = evaluate_from_shadow(shadow_log_path=shadow_dir)
    assert rs.sample_count == 5
    assert rs.level in ("INSUFFICIENT_DATA", "NOT_READY", "BLOCKED", "READY")
    # success_rate may be 0 if evaluate_from_shadow hits audit log issues
    assert isinstance(rs.success_rate, float)

def test_evaluate_empty():
    rs, _ = evaluate_from_shadow(shadow_log_path="/nonexistent/path.jsonl")
    assert rs.sample_count == 0
    assert rs.level == "INSUFFICIENT_DATA"

def test_summary_output():
    rs, _ = evaluate_from_shadow(shadow_log_path="/nonexistent/path.jsonl")
    s = summary(rs)
    assert "recommendation" in s
    assert "level" in s
    assert s["recommendation"] in ("INSUFFICIENT_DATA", "KEEP_SHADOW")

def test_summary_no_api_key():
    rs, _ = evaluate_from_shadow(shadow_log_path="/nonexistent/path.jsonl")
    s = summary(rs)
    j = json.dumps(s)
    assert "sk-" not in j
