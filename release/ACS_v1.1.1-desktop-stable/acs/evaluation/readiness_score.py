"""Readiness score — weighted scoring for on-mode readiness.

Weights:
  success_rate  : 30%
  completeness  : 25%
  stability     : 20%  (1 - severe_error_rate)
  cost_control  : 15%  (1 - cost_ratio)
  safety        : 10%  (api_key_leak=0, old_flow_impact=0)
"""
from dataclasses import dataclass, asdict

WEIGHTS = {
    "success_rate": 0.30,
    "completeness": 0.25,
    "stability": 0.20,
    "cost_control": 0.15,
    "safety": 0.10,
}

@dataclass
class ReadinessScore:
    sample_count: int = 0
    success_rate: float = 0.0
    avg_completeness: float = 0.0
    severe_error_rate: float = 0.0
    cost_ratio: float = 0.0
    api_key_leak_count: int = 0
    old_flow_impact_count: int = 0
    high_risk_pending: int = 0
    score: float = 0.0
    level: str = "INSUFFICIENT_DATA"

    def to_dict(self):
        return asdict(self)

def compute_readiness_score(
    sample_count: int = 0,
    success_rate: float = 0.0,
    avg_completeness: float = 0.0,
    severe_error_rate: float = 0.0,
    cost_ratio: float = 0.0,
    api_key_leak_count: int = 0,
    old_flow_impact_count: int = 0,
    high_risk_pending: int = 0,
) -> ReadinessScore:
    if sample_count < 10:
        return ReadinessScore(sample_count=sample_count, level="INSUFFICIENT_DATA")

    s_success = min(success_rate, 1.0)
    s_completeness = min(avg_completeness, 1.0)
    s_stability = max(0.0, 1.0 - severe_error_rate)
    s_cost = max(0.0, 1.0 - cost_ratio)
    s_safety = 1.0
    if api_key_leak_count > 0: s_safety = 0.0
    if old_flow_impact_count > 0: s_safety = max(0.0, s_safety - 0.5)

    score = (
        WEIGHTS["success_rate"] * s_success +
        WEIGHTS["completeness"] * s_completeness +
        WEIGHTS["stability"] * s_stability +
        WEIGHTS["cost_control"] * s_cost +
        WEIGHTS["safety"] * s_safety
    )

    if api_key_leak_count > 0 or old_flow_impact_count > 0 or high_risk_pending > 0:
        level = "BLOCKED"
    elif sample_count < 100:
        level = "INSUFFICIENT_DATA"
    elif avg_completeness < 0.60:
        level = "NOT_READY"  # hard completeness gate
    elif score >= 0.85:
        level = "READY"
    elif score >= 0.60:
        level = "NOT_READY"
    else:
        level = "NOT_READY"

    return ReadinessScore(
        sample_count=sample_count, success_rate=success_rate,
        avg_completeness=avg_completeness, severe_error_rate=severe_error_rate,
        cost_ratio=cost_ratio, api_key_leak_count=api_key_leak_count,
        old_flow_impact_count=old_flow_impact_count,
        high_risk_pending=high_risk_pending, score=round(score, 4), level=level,
    )
