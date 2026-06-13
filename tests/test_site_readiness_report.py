"""Tests for site readiness report."""
import sys, os, tempfile, shutil, pytest, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.evaluation.site_readiness_report import generate_site_report, SiteReadinessReport

def test_generate_report():
    rpt = generate_site_report(site_id="test", site_name="Test Site")
    assert rpt.site_id == "test"
    assert rpt.site_name == "Test Site"
    assert rpt.recommendation in ("INSUFFICIENT_DATA", "KEEP_SHADOW", "READY_FOR_CANARY")
    assert rpt.readiness_level in ("READY", "NOT_READY", "BLOCKED", "INSUFFICIENT_DATA")

def test_to_dict():
    rpt = generate_site_report("t", "T")
    d = rpt.to_dict()
    assert d["site_id"] == "t"
    assert "blocking_reasons" in d

def test_markdown():
    rpt = generate_site_report("x", "X")
    md = rpt.markdown()
    assert "On-Mode Readiness" in md
    assert "x" in md
    assert "Readiness Score" in md

def test_report_no_api_key():
    rpt = generate_site_report("k", "K")
    j = json.dumps(rpt.to_dict())
    assert "sk-" not in j
    assert "Bearer" not in j
    md = rpt.markdown()
    assert "sk-" not in md
