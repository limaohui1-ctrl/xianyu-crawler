"""Log rotation — archive and trim log files with safety guards."""
import os, sys, json, time, shutil, argparse

SAFE_EXTS = {".jsonl", ".json", ".log", ".db", ".md"}
FORBIDDEN = {".py", ".pyc", ".exe", ".dll", ".so", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".env", ".env.smoke",
             ".gitignore", ".git"}

def rotate_log(src: str, archive_dir: str = "archive", max_keep: int = 5, dry_run: bool = True):
    if not os.path.exists(src): return {"source": src, "status": "skipped", "reason": "does not exist"}
    ext = os.path.splitext(src)[1]
    if ext in FORBIDDEN or any(src.endswith(x) for x in FORBIDDEN):
        return {"source": src, "status": "forbidden", "reason": f"protected file type: {ext}"}
    os.makedirs(archive_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    base = os.path.basename(src)
    dst = os.path.join(archive_dir, f"{base}.{ts}")
    if dry_run:
        size = os.path.getsize(src) if os.path.isfile(src) else 0
        return {"source": src, "destination": dst, "status": "dry_run", "size": size}
    shutil.copy2(src, dst)
    return {"source": src, "destination": dst, "status": "archived", "size": os.path.getsize(src)}

def rotate_logs(log_files: list, archive_dir: str = "archive", dry_run: bool = True) -> list:
    return [rotate_log(f, archive_dir, dry_run=dry_run) for f in log_files]

DEFAULT_LOGS = ["acs_shadow_logs/acs_shadow.jsonl", "logs/ai_call_audit.jsonl", "logs/ai_cost_report.json"]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--dir", default="archive")
    args = p.parse_args()
    dry = not args.execute
    results = rotate_logs(DEFAULT_LOGS, args.dir, dry_run=dry)
    for r in results: print(json.dumps(r, ensure_ascii=False))

if __name__ == "__main__":
    main()
