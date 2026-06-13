"""Tests for risk classifier."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.evaluation.risk_classifier import RiskClassifier
from acs.evaluation.readiness_score import compute_readiness_score

def test_empty_classification():
    rc = RiskClassifier()
    rs = compute_readiness_score(sample_count=0)
    risks = rc.classify(rs)
    assert len(risks) >= 1  # insufficient_samples

def test_low_success_triggers_risk():
    rc = RiskClassifier()
    rs = compute_readiness_score(sample_count=50, success_rate=0.70, avg_completeness=0.50)
    risks = rc.classify(rs)
    names = [r.risk_id for r in risks]
    assert "low_success_rate" in names

def test_blocking_reasons():
    rc = RiskClassifier()
    rs = compute_readiness_score(sample_count=10, success_rate=0.70, avg_completeness=0.40)
    rc.classify(rs)
    reasons = rc.blocking_reasons()
    assert len(reasons) >= 1

def test_api_key_leak_critical():
    rc = RiskClassifier()
    rs = compute_readiness_score(sample_count=100, success_rate=0.90, avg_completeness=0.80, api_key_leak_count=1)
    risks = rc.classify(rs)
    leak = [r for r in risks if r.risk_id == "api_key_leak"]
    assert len(leak) == 1
    assert leak[0].severity == "critical"

def test_to_list():
    rc = RiskClassifier()
    rs = compute_readiness_score(sample_count=10, success_rate=0.70, avg_completeness=0.40)
    rc.classify(rs)
    lst = rc.to_list()
    assert isinstance(lst, list)
    assert all(isinstance(x, dict) for x in lst)
