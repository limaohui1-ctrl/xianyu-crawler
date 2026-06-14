"""Risk classifier — identify blocking risks for on-mode."""
from dataclasses import dataclass, asdict, field
from typing import List

@dataclass
class RiskItem:
    risk_id: str = ""
    category: str = ""
    severity: str = "medium"
    blocking: bool = False
    description: str = ""
    evidence: str = ""
    recommendation: str = ""

    def to_dict(self):
        return asdict(self)

class RiskClassifier:
    def __init__(self):
        self.risks: List[RiskItem] = []

    def add(self, risk_id: str, category: str, severity: str, blocking: bool, description: str, evidence: str = "", recommendation: str = ""):
        self.risks.append(RiskItem(risk_id=risk_id, category=category, severity=severity, blocking=blocking, description=description, evidence=evidence, recommendation=recommendation))

    def classify(self, readiness_score, site_id: str = "") -> List[RiskItem]:
        self.risks.clear()
        s = readiness_score
        if s.sample_count < 100:
            self.add("insufficient_samples", "data", "medium", True, f"Only {s.sample_count} shadow samples, need >=100", str(s.sample_count), "Run more shadow collections")
        if s.sample_count >= 10 and s.success_rate < 0.85:
            self.add("low_success_rate", "quality", "high", True, f"Success rate {s.success_rate:.1%} < 85%", str(s.success_rate), "Improve parsers or add site-specific selectors")
        if s.sample_count >= 10 and s.avg_completeness < 0.60:
            self.add("low_completeness", "quality", "high", True, f"Avg completeness {s.avg_completeness:.1%} < 60%", str(s.avg_completeness), "Check parser coverage for key fields")
        if s.severe_error_rate > 0.05:
            self.add("high_severe_errors", "stability", "high", True, f"Severe error rate {s.severe_error_rate:.1%} > 5%", str(s.severe_error_rate), "Investigate 401/500/timeout errors")
        if s.cost_ratio > 0.80:
            self.add("cost_near_limit", "cost", "medium", True, f"Cost {s.cost_ratio:.0%} of limit", str(s.cost_ratio), "Reduce AI fallback or increase budget")
        if s.api_key_leak_count > 0:
            self.add("api_key_leak", "security", "critical", True, f"API key leaked {s.api_key_leak_count} times", str(s.api_key_leak_count), "Immediate fix required — audit all logs")
        if s.old_flow_impact_count > 0:
            self.add("old_flow_impact", "stability", "critical", True, f"Old flow impacted {s.old_flow_impact_count} times", str(s.old_flow_impact_count), "Isolate ACS from old flow completely")
        return self.risks

    def blocking_reasons(self) -> List[str]:
        return [r.description for r in self.risks if r.blocking]

    def to_list(self) -> list:
        return [r.to_dict() for r in self.risks]
