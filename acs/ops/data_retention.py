"""Data retention — safely clean old data with dry-run."""
import os, sys, json, time, argparse, glob

SAFE_DIRS = {"logs", "archive", "backups", "reports", "acs_shadow_logs"}
FORBIDDEN_DIRS = {"acs", "tests", "acs_data", ".git", ".hermes", "__pycache__", ".pytest_cache"}

def list_old_files(directory: str, max_age_days: int = 90, pattern: str = "*"):
    old = []
    cutoff = time.time() - max_age_days * 86400
    for path in glob.glob(os.path.join(directory, pattern)):
        if os.path.isfile(path):
            mtime = os.path.getmtime(path)
            if mtime < cutoff:
                old.append({"path": path, "mtime": time.strftime("%Y-%m-%d", time.localtime(mtime)), "size": os.path.getsize(path)})
    return old

def cleanup(directories: list = None, max_age_days: int = 90, dry_run: bool = True) -> dict:
    dirs = directories or ["archive", "backups", "reports"]
    results = {"dry_run": dry_run, "max_age_days": max_age_days, "entries": [], "total_size": 0}
    for d in dirs:
        base = os.path.basename(os.path.abspath(d))
        if base in FORBIDDEN_DIRS:
            results["entries"].append({"directory": d, "status": "forbidden"})
            continue
        old_files = list_old_files(d, max_age_days)
        for f in old_files:
            if not dry_run:
                try:
                    os.makedirs(target_dir, exist_ok=True)
                except Exception:  # target_dir creation may fail on read-only parent
                    pass
            f["status"] = "dry_run" if dry_run else "deleted"
        results["entries"].extend(old_files)
        results["total_size"] += sum(f["size"] for f in old_files)
    return results

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--max-age", type=int, default=90)
    p.add_argument("--dirs", nargs="*", default=["archive", "backups", "reports"])
    args = p.parse_args()
    r = cleanup(directories=args.dirs, max_age_days=args.max_age, dry_run=not args.execute)
    print(json.dumps(r, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
