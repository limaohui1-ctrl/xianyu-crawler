"""Canary Monitor — tracks canary metrics during sandbox runs.

Checks: error_rate, completeness_drop, cost_limit.
Triggers: alert on violation, auto-rollback signal.
NEVER auto-applies rules. NEVER sets ACS_MODE=on.
"""
import os, sys, json, time
from dataclasses import dataclass, asdict

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJ = os.path.dirname(os.path.dirname(_HERE))
if _PROJ not in sys.path: sys.path.insert(0, _PROJ)

@dataclass
class CanaryMetrics:
    site_id: str = ""
    checked_at: str = ""
    sample_count: int = 0
    success_rate: float = 0.0
    avg_completeness: float = 0.0
    baseline_completeness: float = 0.60
    error_rate: float = 0.0
    cost_ratio: float = 0.0
    completeness_drop: float = 0.0
    status: str = "ok"
    rollback_signalled: bool = False
    alerts: list = None

    def __post_init__(self):
        if self.alerts is None: self.alerts = []
        if not self.checked_at: self.checked_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    def to_dict(self): return asdict(self)


class CanaryMonitor:
    def __init__(self, site_id: str = "public_test_ecommerce",
                 rollback_on_error_rate: float = 0.05,
                 rollback_on_completeness_drop: float = 0.20,
                 rollback_on_cost_limit: bool = True,
                 baseline_completeness: float = 0.60):
        self.site_id = site_id
        self.rollback_on_error_rate = rollback_on_error_rate
        self.rollback_on_completeness_drop = rollback_on_completeness_drop
        self.rollback_on_cost_limit = rollback_on_cost_limit
        self.baseline_completeness = baseline_completeness
        self.history: list = []

    def check(self) -> CanaryMetrics:
        m = CanaryMetrics(site_id=self.site_id, baseline_completeness=self.baseline_completeness)

        # Load shadow data
        try:
            shadow_path = "acs_shadow_logs/acs_shadow.jsonl"
            if os.path.exists(shadow_path):
                with open(shadow_path, encoding="utf-8") as f:
                    entries = [json.loads(l) for l in f if l.strip()]
                recent = entries[-100:] if len(entries) >= 100 else entries
                m.sample_count = len(recent)
                if recent:
                    m.success_rate = sum(1 for e in recent if e.get("acs_success")) / len(recent)
                    comps = [e.get("acs_completeness", 0) for e in recent if e.get("acs_success")]
                    m.avg_completeness = sum(comps) / max(len(comps), 1)
                    m.error_rate = sum(1 for e in recent if e.get("acs_error")) / len(recent)
        except Exception:
            pass

        # Load cost
        try:
            cost_path = "logs/ai_cost_report.json"
            if os.path.exists(cost_path):
                with open(cost_path, encoding="utf-8") as f:
                    cost = json.load(f)
                m.cost_ratio = min(cost.get("estimated_cost", 0) / 0.50, 1.0)
        except Exception:
            pass

        # Completeness drop
        m.completeness_drop = max(0, m.baseline_completeness - m.avg_completeness / 100.0)

        # ── Check rollback conditions ──
        if m.error_rate > self.rollback_on_error_rate:
            m.alerts.append(f"ERROR_RATE {m.error_rate:.1%} > {self.rollback_on_error_rate:.0%}")
            m.rollback_signalled = True
        if m.completeness_drop > self.rollback_on_completeness_drop:
            m.alerts.append(f"COMPLETENESS_DROP {m.completeness_drop:.1%} > {self.rollback_on_completeness_drop:.0%}")
            m.rollback_signalled = True
        if self.rollback_on_cost_limit and m.cost_ratio > 0.80:
            m.alerts.append(f"COST_LIMIT {m.cost_ratio:.0%}")
            m.rollback_signalled = True

        if m.rollback_signalled:
            m.status = "rollback_triggered"
        elif m.alerts:
            m.status = "warning"
        else:
            m.status = "ok"

        self.history.append(m)
        return m

    def summary(self) -> dict:
        if not self.history:
            return {"site_id": self.site_id, "checks": 0, "status": "no_data"}
        last = self.history[-1]
        return {
            "site_id": self.site_id,
            "checks": len(self.history),
            "last_check": last.checked_at,
            "status": last.status,
            "rollback_signalled": last.rollback_signalled,
            "error_rate": last.error_rate,
            "completeness_drop": last.completeness_drop,
            "alerts": last.alerts,
        }

    def to_list(self) -> list:
        return [m.to_dict() for m in self.history]
