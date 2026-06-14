"""Tests for rollback_executor — dry-run, execute, verify shadow."""
import sys, os, json, tempfile, shutil, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.ops.rollback_executor import RollbackExecutor, RollbackReport, ROLLBACK_STEPS

def test_rollback_steps_complete():
    assert len(ROLLBACK_STEPS) >= 8
    assert any("ACS_MODE=shadow" in s for s in ROLLBACK_STEPS)

def test_rollback_dry_run():
    exe = RollbackExecutor("test_site")
    r = exe.dry_run()
    assert r["dry_run"] is True
    assert len(r["steps"]) == len(ROLLBACK_STEPS)

def test_rollback_execute_dry_run_flag():
    exe = RollbackExecutor("test_site")
    r = exe.execute(reason="test", dry_run_only=True)
    assert r["dry_run"] is True

def test_rollback_execute():
    exe = RollbackExecutor("test_site")
    r = exe.execute(reason="test_dry_run", dry_run_only=False)
    assert r["status"] == "rolled_back"

def test_rollback_sets_shadow_mode():
    import os
    old = os.environ.get("ACS_MODE", "shadow")
    exe = RollbackExecutor("test_site")
    exe.execute(reason="test", dry_run_only=False)
    mode = os.environ.get("ACS_MODE", "shadow")
    assert mode == "shadow"
    assert mode != "on"
    os.environ["ACS_MODE"] = old

def test_rollback_report_create():
    rpt = RollbackReport(site_id="test", reason="test")
    assert rpt.acs_mode_after == "shadow"
    assert rpt.legacy_output == "official"
    assert rpt.ai_parser_output == "shadow_only"
    assert rpt.self_healing == "pending_review_only"

def test_rollback_report_markdown():
    rpt = RollbackReport(site_id="test", reason="test")
    md = rpt.markdown()
    assert "Rollback Report" in md
    assert "ACS_MODE=shadow" in md

def test_rollback_report_no_api_key():
    rpt = RollbackReport(site_id="k", reason="r")
    j = json.dumps(rpt.to_dict())
    assert "sk-" not in j
    assert "Bearer" not in j
