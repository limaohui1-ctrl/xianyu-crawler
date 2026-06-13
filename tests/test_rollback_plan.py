"""Tests for rollback plan."""
import sys, os, pytest, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.evaluation.rollback_plan import RollbackPlan, DEFAULT_ROLLBACK, generate_rollback_plan

def test_default_rollback():
    rp = DEFAULT_ROLLBACK
    assert rp.rollback_target == "ACS_MODE=shadow"
    assert rp.legacy_output == "official"
    assert len(rp.steps) >= 5

def test_generate_rollback():
    rp = generate_rollback_plan("example.com")
    assert rp.site_id == "example.com"
    assert rp.verified is False

def test_to_dict():
    rp = RollbackPlan(site_id="x")
    d = rp.to_dict()
    assert d["site_id"] == "x"
    assert d["rollback_target"] == "ACS_MODE=shadow"

def test_markdown():
    rp = RollbackPlan(site_id="t")
    md = rp.markdown()
    assert "Rollback Plan" in md
    assert "ACS_MODE=shadow" in md

def test_rollback_plan_no_api_key():
    rp = RollbackPlan(site_id="k")
    j = json.dumps(rp.to_dict())
    assert "sk-" not in j
    assert "Bearer" not in j
