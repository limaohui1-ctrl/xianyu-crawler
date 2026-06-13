"""Backup manager — backup databases and logs with safety."""
import os, sys, json, time, shutil, argparse

EXCLUDE = {".env", ".env.smoke", ".gitignore", ".git", "__pycache__", ".pytest_cache"}

BACKUP_ITEMS = [
    ("acs_data/reviews.db", "databases/"),
    ("acs_data/structure_history.db", "databases/"),
    ("acs_data/dedup.db", "databases/"),
    ("acs_shadow_logs/acs_shadow.jsonl", "logs/"),
    ("logs/ai_call_audit.jsonl", "logs/"),
    ("logs/ai_cost_report.json", "logs/"),
    ("reports/", "reports/"),
]

def backup(target_dir: str = "backups", dry_run: bool = True) -> dict:
    results = []
    ts = time.strftime("%Y%m%d-%H%M%S")
    for src, category in BACKUP_ITEMS:
        if not os.path.exists(src):
            results.append({"source": src, "status": "skipped", "reason": "not found"})
            continue
        dst_dir = os.path.join(target_dir, ts, category)
        if dry_run:
            size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, files in os.walk(src) for f in files) if os.path.isdir(src) else os.path.getsize(src)
            results.append({"source": src, "destination_dir": dst_dir, "status": "dry_run", "size": size})
            continue
        os.makedirs(dst_dir, exist_ok=True)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(dst_dir, os.path.basename(src)), dirs_exist_ok=True,
                            ignore=lambda d, files: [f for f in files if f in EXCLUDE])
        else:
            shutil.copy2(src, os.path.join(dst_dir, os.path.basename(src)))
        results.append({"source": src, "destination_dir": dst_dir, "status": "backed_up"})
    return {"target": os.path.join(target_dir, ts), "dry_run": dry_run, "items": results}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--dir", default="backups")
    args = p.parse_args()
    r = backup(target_dir=args.dir, dry_run=not args.execute)
    print(json.dumps(r, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
