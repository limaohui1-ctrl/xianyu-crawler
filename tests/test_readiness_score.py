"""Tests for readiness score computation."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.evaluation.readiness_score import compute_readiness_score, ReadinessScore

def test_insufficient_data_zero():
    rs = compute_readiness_score(sample_count=0)
    assert rs.level == "INSUFFICIENT_DATA"

def test_insufficient_data_below10():
    rs = compute_readiness_score(sample_count=5, success_rate=0.9, avg_completeness=0.7)
    assert rs.level == "INSUFFICIENT_DATA"

def test_insufficient_data_below100():
    rs = compute_readiness_score(sample_count=50, success_rate=0.9, avg_completeness=0.7)
    assert rs.level == "INSUFFICIENT_DATA"

def test_ready_at_100():
    rs = compute_readiness_score(sample_count=100, success_rate=0.90, avg_completeness=0.70, severe_error_rate=0.02)
    assert rs.level == "READY"

def test_not_ready_low_success():
    rs = compute_readiness_score(sample_count=150, success_rate=0.70, avg_completeness=0.70)
    assert rs.level == "NOT_READY"

def test_blocked_api_key_leak():
    rs = compute_readiness_score(sample_count=200, success_rate=0.95, avg_completeness=0.85, api_key_leak_count=1)
    assert rs.level == "BLOCKED"

def test_blocked_old_flow_impact():
    rs = compute_readiness_score(sample_count=200, success_rate=0.95, avg_completeness=0.85, old_flow_impact_count=1)
    assert rs.level == "BLOCKED"

def test_blocked_high_risk_pending():
    rs = compute_readiness_score(sample_count=200, success_rate=0.95, avg_completeness=0.85, high_risk_pending=3)
    assert rs.level == "BLOCKED"

def test_score_range():
    rs = compute_readiness_score(sample_count=100, success_rate=0.85, avg_completeness=0.60)
    assert 0 <= rs.score <= 1.0

def test_to_dict():
    rs = compute_readiness_score(sample_count=10, success_rate=0.5, avg_completeness=0.3)
    d = rs.to_dict()
    assert d["level"] in ("NOT_READY", "INSUFFICIENT_DATA")
