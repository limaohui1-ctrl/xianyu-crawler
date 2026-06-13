"""Canary plan — gradual on-mode rollout plan. NEVER auto-executes."""
from dataclasses import dataclass, asdict
import json, time

@dataclass
class CanaryPlan:
    site_id: str = ""
    canary_ratio: float = 0.05
    duration_hours: int = 24
    rollback_on_error_rate: float = 0.05
    rollback_on_completeness_drop: float = 0.20
    rollback_on_cost_limit: bool = True
    manual_approval_required: bool = True
    max_urls: int = 10
    ai_fallback_enabled: bool = False
    created_at: str = ""
    status: str = "draft"
    notes: str = ""

    def __post_init__(self):
        if not self.created_at: self.created_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    def to_dict(self):
        return asdict(self)

    def markdown(self) -> str:
        return f"""# Canary Plan: {self.site_id}

| Property | Value |
| -------- | ----- |
| Canary Ratio | {self.canary_ratio:.0%} |
| Duration | {self.duration_hours}h |
| Max URLs | {self.max_urls} |
| Rollback on error rate > | {self.rollback_on_error_rate:.0%} |
| Rollback on completeness drop > | {self.rollback_on_completeness_drop:.0%} |
| Rollback on cost limit | {self.rollback_on_cost_limit} |
| Manual approval required | {self.manual_approval_required} |
| AI fallback enabled | {self.ai_fallback_enabled} |
| Status | {self.status} |

> **DO NOT EXECUTE without manual approval. ACS_MODE must stay shadow.**
"""

DEFAULT_CANARY = CanaryPlan(
    site_id="default",
    canary_ratio=0.05,
    duration_hours=24,
    rollback_on_error_rate=0.05,
    rollback_on_completeness_drop=0.20,
    rollback_on_cost_limit=True,
    manual_approval_required=True,
    max_urls=10,
    ai_fallback_enabled=False,
    status="draft",
    notes="Auto-generated canary plan. Manual approval required before execution.",
)

def generate_canary_plan(site_id: str = "default", **overrides) -> CanaryPlan:
    plan = DEFAULT_CANARY
    plan.site_id = site_id
    for k, v in overrides.items():
        if hasattr(plan, k): setattr(plan, k, v)
    return plan
