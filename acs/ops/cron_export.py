"""Cron export — scheduled export of reports."""
import os, sys, json, time, shutil
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJ = os.path.dirname(os.path.dirname(_HERE))
if _PROJ not in sys.path: sys.path.insert(0, _PROJ)

def export_all(target_dir: str = "reports/export"):
    os.makedirs(target_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    results = {}
    # Export dashboard report
    try:
        from acs.dashboard.report_builder import ReportBuilder
        b = ReportBuilder()
        d = b.build_dict()
        path = os.path.join(target_dir, f"dashboard_{ts}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        results["dashboard"] = path
    except Exception as e:
        results["dashboard_error"] = str(e)
    # Copy audit log
    for src, key in [("logs/ai_call_audit.jsonl", "audit"), ("logs/ai_cost_report.json", "cost")]:
        if os.path.exists(src):
            dst = os.path.join(target_dir, f"{key}_{ts}.jsonl" if key == "audit" else f"{key}_{ts}.json")
            shutil.copy2(src, dst)
            results[key] = dst
    return results

if __name__ == "__main__":
    r = export_all()
    print(json.dumps(r, ensure_ascii=False, indent=2))
