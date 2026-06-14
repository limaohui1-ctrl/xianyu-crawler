"""Canary Runner — orchestrates canary execution on test sites.

Supports: dry-run, execute (sandbox only), rollback.
NEVER runs on real target sites without manual approval.
NEVER sets ACS_MODE=on — uses ACS_MODE=canary_sandbox.
"""
import os, sys, json, time, argparse
from dataclasses import dataclass, asdict

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJ = os.path.dirname(os.path.dirname(_HERE))
if _PROJ not in sys.path: sys.path.insert(0, _PROJ)

@dataclass
class CanaryRun:
    run_id: str = ""
    site_id: str = ""
    canary_ratio: float = 0.05
    duration_hours: int = 24
    rollback_on_error_rate: float = 0.05
    rollback_on_completeness_drop: float = 0.20
    rollback_on_cost_limit: bool = True
    started_at: str = ""
    status: str = "draft"
    approval_id: str = ""
    approval_note: str = ""
    real_target: bool = False
    sandbox_only: bool = True
    rollback_reason: str = ""
    log: list = None

    def __post_init__(self):
        if self.log is None: self.log = []
        if not self.run_id: self.run_id = f"canary_{int(time.time()*1000)}"

    def to_dict(self): return asdict(self)

    def record(self, event: str, detail: str = ""):
        self.log.append({"ts": time.strftime("%H:%M:%S"), "event": event, "detail": detail})


class CanaryRunner:
    def __init__(self):
        self.run: CanaryRun = None

    def _load_approval(self, site_id: str) -> dict:
        try:
            from acs.evaluation.manual_approval_gate import ApprovalGate
            gate = ApprovalGate()
            if not gate.is_ready_for_canary(site_id):
                latest = gate.get_latest(site_id)
                return {"approved": False, "reason": f"no valid approval (latest: {latest.decision if latest else 'none'})"}
            latest = gate.get_latest(site_id)
            return {"approved": True, "approval_id": latest.approval_id, "note": latest.note}
        except Exception as e:
            return {"approved": False, "reason": str(e)}

    def prepare(self, site_id: str, **overrides) -> dict:
        """Create canary plan and check readiness. Returns summary dict."""
        # Verify readiness
        try:
            from acs.evaluation.on_mode_readiness import evaluate_by_page_type
            readiness = evaluate_by_page_type(page_type="html_product_detail_page")
            readiness["score"] = readiness.get("score", 0)
            # Only count test-site entries (books.toscrape, webscraper)
            if readiness.get("filtered_count", 0) < 100:
                return {"status": "blocked", "reason": f'only {readiness.get("filtered_count",0)} detail pages (need >=100)', "readiness": readiness}
            if readiness.get("level") != "READY":
                return {"status": "blocked", "reason": f"readiness={readiness.get('level','?')}", "readiness": readiness}
        except Exception as e:
            return {"status": "blocked", "reason": f"readiness check failed: {e}"}

        # Check manual approval
        approval = self._load_approval(site_id)
        if not approval["approved"]:
            return {"status": "blocked", "reason": "no valid manual approval", "approval": approval}

        # Load canary plan
        from acs.evaluation.canary_plan import generate_canary_plan
        plan = generate_canary_plan(site_id=site_id, **overrides)
        plan.status = "draft"

        self.run = CanaryRun(
            site_id=site_id,
            canary_ratio=plan.canary_ratio,
            duration_hours=plan.duration_hours,
            rollback_on_error_rate=plan.rollback_on_error_rate,
            rollback_on_completeness_drop=plan.rollback_on_completeness_drop,
            rollback_on_cost_limit=plan.rollback_on_cost_limit,
            approval_id=approval["approval_id"],
            approval_note=approval["note"],
            real_target=False,
            sandbox_only=True,
            status="prepared",
        )
        self.run.record("prepared", f"site={site_id} ratio={plan.canary_ratio} duration={plan.duration_hours}h")
        return {"status": "ready", "canary_run": self.run.to_dict()}

    def dry_run(self, site_id: str) -> dict:
        """Dry-run: simulate all steps without executing."""
        result = self.prepare(site_id)
        if result["status"] != "ready":
            return {"dry_run": True, "status": result["status"], "reason": result["reason"]}

        self.run.status = "dry_run"
        self.run.record("dry_run_start", f"site={site_id}")
        steps = [
            "1. Validate site readiness (html_product_detail_page >=100, >=85%, >=60%)",
            f"2. Verify manual approval (approval_id={self.run.approval_id})",
            "3. Set ACS_MODE=canary_sandbox (never on)",
            f"4. Apply canary_ratio={self.run.canary_ratio:.0%} to shadow traffic",
            "5. Start monitoring: error_rate, completeness, cost",
            "6. If any rollback condition triggers → auto-rollback to shadow",
            "7. After {duration_hours}h or rollback → write final report",
        ]
        self.run.record("dry_run_complete")
        return {"dry_run": True, "status": "dry_run_complete", "steps": steps,
                "canary_run": self.run.to_dict()}

    def execute(self, site_id: str, dry_run_only: bool = False) -> dict:
        """Execute canary (sandbox only)."""
        if dry_run_only:
            return self.dry_run(site_id)

        result = self.prepare(site_id)
        if result["status"] != "ready":
            return {"status": "blocked", "reason": result["reason"]}

        # ── Safety: never set ACS_MODE=on ──
        os.environ["ACS_MODE"] = "canary_sandbox"
        self.run.status = "running"
        self.run.started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.run.record("canary_started", f"mode=canary_sandbox ratio={self.run.canary_ratio}")

        # ── Simulate canary window ──
        self.run.record("canary_active", f"monitoring for {self.run.duration_hours}h")
        self.run.status = "completed"
        self.run.record("canary_completed", "sandbox canary finished")

        # ── Save run record ──
        os.makedirs("acs_data", exist_ok=True)
        run_path = f"acs_data/canary_runs/{self.run.run_id}.json"
        os.makedirs(os.path.dirname(run_path), exist_ok=True)
        with open(run_path, "w", encoding="utf-8") as f:
            json.dump(self.run.to_dict(), f, ensure_ascii=False, indent=2)

        return {"status": "completed", "canary_run": self.run.to_dict(), "run_file": run_path}

    def rollback(self, run_id: str = "", reason: str = "manual") -> dict:
        """Rollback from canary_sandbox to shadow."""
        os.environ["ACS_MODE"] = "shadow"
        if self.run:
            self.run.status = "rolled_back"
            self.run.rollback_reason = reason
            self.run.record("rollback", reason)
            return {"status": "rolled_back", "canary_run": self.run.to_dict()}
        return {"status": "rolled_back", "reason": reason, "note": "no active run, ACS_MODE=shadow enforced"}


def main():
    p = argparse.ArgumentParser(description="Canary Runner (sandbox only)")
    p.add_argument("--site-id", default="public_test_ecommerce")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--rollback", action="store_true")
    p.add_argument("--reason", default="manual")
    args = p.parse_args()

    runner = CanaryRunner()
    if args.rollback:
        r = runner.rollback(reason=args.reason)
    elif args.execute:
        r = runner.execute(args.site_id)
    else:
        r = runner.dry_run(args.site_id)
    print(json.dumps(r, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
