"""Rollback plan — return from canary/on to shadow. NEVER auto-executes."""
from dataclasses import dataclass, asdict
import json, time

@dataclass
class RollbackPlan:
    site_id: str = ""
    rollback_target: str = "ACS_MODE=shadow"
    legacy_output: str = "official"
    ai_parser_output: str = "shadow_only"
    self_healing: str = "pending_review_only"
    steps: list = None
    created_at: str = ""
    verified: bool = False

    def __post_init__(self):
        if self.steps is None:
            self.steps = [
                "1. Set ACS_MODE=shadow in environment",
                "2. Confirm legacy flow is the only official output",
                "3. Disable AI parser fallback for production",
                "4. Set all self-healing rules to pending_review_only",
                "5. Export shadow logs for post-mortem analysis",
                "6. Restore site config from backup if modified",
                "7. Run adapter + self-test + pytest to confirm",
                "8. Verify Dashboard shows ACS_MODE=shadow",
            ]
        if not self.created_at: self.created_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    def to_dict(self):
        return asdict(self)

    def markdown(self) -> str:
        steps_md = "\n".join(self.steps)
        return f"""# Rollback Plan: {self.site_id}

| Property | Value |
| -------- | ----- |
| Target | {self.rollback_target} |
| Legacy Output | {self.legacy_output} |
| AI Parser Output | {self.ai_parser_output} |
| Self-Healing | {self.self_healing} |
| Verified | {self.verified} |

## Steps
{steps_md}

> Execute ONLY if canary/on-mode fails or triggers rollback conditions.
"""

DEFAULT_ROLLBACK = RollbackPlan(site_id="default")

def generate_rollback_plan(site_id: str = "default") -> RollbackPlan:
    return RollbackPlan(site_id=site_id, verified=False)
