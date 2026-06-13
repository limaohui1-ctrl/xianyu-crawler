"""Scheduler — daily/weekly report generation with cron/Windows task export."""
import os, sys, json, time, argparse, datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJ = os.path.dirname(os.path.dirname(_HERE))
if _PROJ not in sys.path: sys.path.insert(0, _PROJ)

PYTHON = sys.executable
SCRIPT = os.path.join(_PROJ, "acs", "ops", "scheduler.py")

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
        md = r.markdown(); fname = f"{out_dir}/daily_{r.date}.md"; json_name = f"{out_dir}/daily_{r.date}.json"
    else:
        from acs.ops.daily_report import generate_daily as gd
        from acs.ops.weekly_report import generate_weekly
        d1 = gd(shadow=shadow, cost=cost, reviews=reviews, audit=audit)
        r = generate_weekly(dailies=[d1])
        md = r.markdown(); fname = f"{out_dir}/weekly_{ts}.md"; json_name = f"{out_dir}/weekly_{ts}.json"
    with open(fname, "w", encoding="utf-8") as f: f.write(md)
    with open(json_name, "w", encoding="utf-8") as f: json.dump(r.to_dict(), f, ensure_ascii=False, indent=2)
    return {"report_type": report_type, "markdown": fname, "json": json_name, "summary": r.to_dict()}

def next_run_time(hour: int, minute: int, weekday: int = -1) -> str:
    """Calculate next run time in ISO format. weekday: 0=Mon..6=Sun, -1=daily."""
    now = datetime.datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if weekday >= 0:
        days_ahead = weekday - now.weekday()
        if days_ahead <= 0: days_ahead += 7
        target = (now + datetime.timedelta(days=days_ahead)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    elif target <= now:
        target += datetime.timedelta(days=1)
    return target.isoformat()

def export_cron(daily_time="08:00", weekly_day="monday", weekly_time="09:00") -> dict:
    """Export cron expressions and commands."""
    weekday_map = {"monday":1,"tuesday":2,"wednesday":3,"thursday":4,"friday":5,"saturday":6,"sunday":0}
    wd = weekday_map.get(weekly_day.lower(), 1)
    dh, dm = map(int, daily_time.split(":"))
    wh, wm = map(int, weekly_time.split(":"))
    cd = os.path.abspath(_PROJ).replace("\\", "/")
    return {
        "daily_cron": f"{dm} {dh} * * *",
        "daily_command": f'{PYTHON} -m acs.ops.scheduler --daily',
        "daily_crontab": f'{dm} {dh} * * * cd "{cd}" && {PYTHON} -m acs.ops.scheduler --daily',
        "weekly_cron": f"{wm} {wh} * * {wd}",
        "weekly_command": f'{PYTHON} -m acs.ops.scheduler --weekly',
        "weekly_crontab": f'{wm} {wh} * * {wd} cd "{cd}" && {PYTHON} -m acs.ops.scheduler --weekly',
        "next_daily_run": next_run_time(dh, dm),
        "next_weekly_run": next_run_time(wh, wm, wd),
    }

def export_windows_task(daily_time="08:00", weekly_day="monday", weekly_time="09:00"):
    """Export Windows Task Scheduler XML / schtasks commands."""
    weekday_map = {"monday":"MON","tuesday":"TUE","wednesday":"WED","thursday":"THU","friday":"FRI","saturday":"SAT","sunday":"SUN"}
    wd = weekday_map.get(weekly_day.lower(), "MON")
    cd = os.path.abspath(_PROJ)
    return {
        "daily_schtasks": f'schtasks /create /tn "ACS_Daily_Report" /tr "\"{PYTHON}\" -m acs.ops.scheduler --daily" /sc DAILY /st {daily_time} /f',
        "weekly_schtasks": f'schtasks /create /tn "ACS_Weekly_Report" /tr "\"{PYTHON}\" -m acs.ops.scheduler --weekly" /sc WEEKLY /d {wd} /st {weekly_time} /f',
        "working_dir": cd,
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--daily", action="store_true"); p.add_argument("--weekly", action="store_true")
    p.add_argument("--schedule", choices=["daily","weekly"], default="")
    p.add_argument("--weekday", default="monday"); p.add_argument("--time", default="09:00")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--export-cron", action="store_true")
    p.add_argument("--export-windows-task", action="store_true")
    args = p.parse_args()

    if args.export_cron:
        r = export_cron(daily_time=args.time, weekly_day=args.weekday, weekly_time=args.time)
        print(json.dumps(r, ensure_ascii=False, indent=2))
    elif args.export_windows_task:
        r = export_windows_task(daily_time=args.time, weekly_day=args.weekday, weekly_time=args.time)
        print(json.dumps(r, ensure_ascii=False, indent=2))
    elif args.schedule and args.dry_run:
        rt = args.schedule
        hour, minute = map(int, args.time.split(":"))
        wd = -1 if rt == "daily" else {"monday":0,"tuesday":1,"wednesday":2,"thursday":3,"friday":4,"saturday":5,"sunday":6}.get(args.weekday,0)
        nr = next_run_time(hour, minute, wd)
        print(json.dumps({"report_type": rt, "dry_run": True, "schedule_time": args.time,
                          "weekday": args.weekday, "next_run": nr}, ensure_ascii=False, indent=2))
    elif args.daily or args.schedule == "daily":
        r = generate_and_save("daily")
        print(json.dumps(r, ensure_ascii=False, indent=2))
    elif args.weekly or args.schedule == "weekly":
        r = generate_and_save("weekly")
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print("Usage: --daily | --weekly | --schedule daily|weekly [--time HH:MM] [--dry-run] [--export-cron] [--export-windows-task]")

if __name__ == "__main__":
    main()
