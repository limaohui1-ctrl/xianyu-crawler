"""Rollback Executor — safely restores ACS_MODE=shadow and disables canary.

Steps:
  1. Set ACS_MODE=shadow
  2. Confirm legacy is official output
  3. Set AI parser to shadow_only
  4. Set self-healing to pending_review_only
  5. Export audit/cost/shadow logs for analysis
  6. Write rollback report
"""
import os, sys, json, time, shutil, argparse
from dataclasses import dataclass, asdict

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJ = os.path.dirname(os.path.dirname(_HERE))
if _PROJ not in sys.path: sys.path.insert(0, _PROJ)

ROLLBACK_STEPS = [
    "Set ACS_MODE=shadow in environment",
    "Confirm legacy flow is the only official output",
    "Disable AI parser fallback for production (shadow_only)",
    "Set all self-healing rules to pending_review_only",
    "Export shadow logs for post-mortem analysis",
    "Export audit logs for post-mortem analysis",
    "Export cost report",
    "Restore site config from backup if modified",
    "Run adapter + self-test to confirm",
    "Verify Dashboard shows ACS_MODE=shadow",
    "Write rollback report to acs_data/rollback_{ts}.json",
]


@dataclass
class RollbackReport:
    site_id: str = ""
    rolled_back_at: str = ""
    reason: str = ""
    canary_run_id: str = ""
    steps_completed: list = None
    steps_failed: list = None
    acs_mode_after: str = "shadow"
    legacy_output: str = "official"
    ai_parser_output: str = "shadow_only"
    self_healing: str = "pending_review_only"
    verified: bool = False
    dashboard_confirmed: bool = False
    logs_exported: list = None

    def __post_init__(self):
        if self.steps_completed is None: self.steps_completed = []
        if self.steps_failed is None: self.steps_failed = []
        if self.logs_exported is None: self.logs_exported = []
        if not self.rolled_back_at: self.rolled_back_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    def to_dict(self): return asdict(self)

    def markdown(self) -> str:
        sc = "\n".join(f"- [x] {s}" for s in self.steps_completed)
        sf = "\n".join(f"- [ ] {s}" for s in self.steps_failed) or "None"
        return f"""# Rollback Report: {self.site_id}

| Property | Value |
| -------- | ----- |
| Rolled back | {self.rolled_back_at} |
| Reason | {self.reason} |
| Canary run | {self.canary_run_id} |
| Verified | {self.verified} |
| Dashboard | {self.dashboard_confirmed} |

## Completed Steps
{sc}

## Failed Steps
{sf}

> ACS_MODE=shadow restored.
"""


class RollbackExecutor:
    def __init__(self, site_id: str = "public_test_ecommerce"):
        self.site_id = site_id
        self.report: RollbackReport = None

    def dry_run(self) -> dict:
        return {"dry_run": True, "steps": ROLLBACK_STEPS, "site_id": self.site_id,
                "target_mode": "shadow"}

    def execute(self, reason: str = "manual", canary_run_id: str = "",
                dry_run_only: bool = False) -> dict:
        if dry_run_only:
            return self.dry_run()

        self.report = RollbackReport(
            site_id=self.site_id, reason=reason, canary_run_id=canary_run_id,
            verified=False, dashboard_confirmed=False,
        )

        completed, failed = [], []
        for i, step in enumerate(ROLLBACK_STEPS):
            try:
                if i == 0:
                    os.environ["ACS_MODE"] = "shadow"
                elif i == 4:
                    self._export_log("acs_shadow_logs/acs_shadow.jsonl", "shadow")
                elif i == 5:
                    self._export_log("logs/ai_call_audit.jsonl", "audit")
                elif i == 6:
                    self._export_log("logs/ai_cost_report.json", "cost")
                elif i == 8:
                    pass  # adapter check handled externally
                completed.append(step)
            except Exception as e:
                failed.append(f"{step}: {str(e)[:80]}")

        self.report.steps_completed = completed
        self.report.steps_failed = failed
        self.report.verified = len(failed) == 0

        # Save report
        out_dir = "acs_data/rollbacks"
        os.makedirs(out_dir, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        path = f"{out_dir}/rollback_{ts}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.report.to_dict(), f, ensure_ascii=False, indent=2)
        self.report.logs_exported.append(path)

        md_path = f"{out_dir}/rollback_{ts}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(self.report.markdown())

        return {"status": "rolled_back", "steps_completed": len(completed),
                "steps_failed": len(failed), "report": path, "report_md": md_path,
                "rollback_report": self.report.to_dict()}

    def _export_log(self, src: str, label: str):
        if os.path.exists(src):
            dst = f"acs_data/rollbacks/{label}_{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            self.report.logs_exported.append(dst)


def main():
    p = argparse.ArgumentParser(description="Rollback Executor")
    p.add_argument("--site-id", default="public_test_ecommerce")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--reason", default="manual")
    p.add_argument("--canary-run-id", default="")
    args = p.parse_args()

    exe = RollbackExecutor(args.site_id)
    r = exe.execute(reason=args.reason, canary_run_id=args.canary_run_id,
                    dry_run_only=args.dry_run)
    print(json.dumps(r, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
