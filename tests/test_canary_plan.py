"""Tests for canary plan."""
import sys, os, pytest, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.evaluation.canary_plan import CanaryPlan, DEFAULT_CANARY, generate_canary_plan

def test_default_canary():
    cp = DEFAULT_CANARY
    assert cp.canary_ratio == 0.05
    assert cp.manual_approval_required is True
    assert cp.ai_fallback_enabled is False
    assert cp.status == "draft"

def test_generate_canary():
    cp = generate_canary_plan("example.com", canary_ratio=0.10)
    assert cp.site_id == "example.com"
    assert cp.canary_ratio == 0.10

def test_to_dict():
    cp = CanaryPlan(site_id="x")
    d = cp.to_dict()
    assert d["site_id"] == "x"
    assert d["manual_approval_required"] is True

def test_markdown():
    cp = CanaryPlan(site_id="t")
    md = cp.markdown()
    assert "Canary Plan" in md
    assert "t" in md
    assert "rollback" in md.lower()

def test_canary_plan_no_api_key():
    cp = CanaryPlan(site_id="k")
    j = json.dumps(cp.to_dict())
    assert "sk-" not in j
    assert "Bearer" not in j
