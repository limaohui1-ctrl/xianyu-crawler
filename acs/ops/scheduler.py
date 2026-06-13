"""Scheduler — daily/weekly report generation."""
import os, sys, json, time, argparse
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJ = os.path.dirname(os.path.dirname(_HERE))
if _PROJ not in sys.path: sys.path.insert(0, _PROJ)

def generate_and_save(report_type="daily"):
    from acs.observability.shadow_analyzer import ShadowAnalyzer
    from acs.observability.ai_call_audit import AICallAuditor
    sa = ShadowAnalyzer("acs_shadow_logs/acs_shadow.jsonl")
    shadow = sa.analyze().to_dict()
    auditor = AICallAuditor("logs/ai_call_audit.jsonl")
    audit = auditor.get_stats()
    reviews = {"by_status": {}}
    try:
        from acs.storage.repair_review_store import RepairReviewStore
        rs = RepairReviewStore("acs_data/reviews.db")
        reviews = rs.get_stats()
    except: pass
    cost = {"total_ai_calls": audit.get("total_calls",0), "total_tokens": audit.get("total_tokens",0),
            "estimated_cost": audit.get("estimated_cost",0)}
    out_dir = f"reports/{report_type}"
    os.makedirs(out_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    if report_type == "daily":
        from acs.ops.daily_report import generate_daily
        r = generate_daily(shadow=shadow, cost=cost, reviews=reviews, audit=audit)
        md = r.markdown()
        fname = f"{out_dir}/daily_{r.date}.md"
        json_name = f"{out_dir}/daily_{r.date}.json"
    else:
        from acs.ops.daily_report import generate_daily as gd
        from acs.ops.weekly_report import generate_weekly
        d1 = gd(shadow=shadow, cost=cost, reviews=reviews, audit=audit)
        r = generate_weekly(dailies=[d1])
        md = r.markdown()
        fname = f"{out_dir}/weekly_{ts}.md"
        json_name = f"{out_dir}/weekly_{ts}.json"
    with open(fname, "w", encoding="utf-8") as f: f.write(md)
    with open(json_name, "w", encoding="utf-8") as f:
        json.dump(r.to_dict(), f, ensure_ascii=False, indent=2)
    return {"report_type": report_type, "markdown": fname, "json": json_name, "summary": r.to_dict()}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--daily", action="store_true")
    p.add_argument("--weekly", action="store_true")
    p.add_argument("--schedule", choices=["daily","weekly"], default="")
    args = p.parse_args()
    if args.daily or args.schedule == "daily":
        r = generate_and_save("daily")
        print(json.dumps(r, ensure_ascii=False, indent=2))
    elif args.weekly or args.schedule == "weekly":
        r = generate_and_save("weekly")
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print("Usage: --daily | --weekly | --schedule daily|weekly")

if __name__ == "__main__":
    main()
