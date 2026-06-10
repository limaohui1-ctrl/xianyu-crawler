"""Verify generated runtime/build artifacts are not tracked by git."""

import fnmatch
import subprocess
import sys
from pathlib import Path


FORBIDDEN_DIR_NAMES = {
    "build",
    "dist",
    "self_test_runtime",
    "self_test_runtime_probe",
    "chrome-profile",
    "采集结果导出",
}
FORBIDDEN_DIR_PREFIXES = ("build_", "dist_")
FORBIDDEN_FILE_NAMES = {
    "app_settings.json",
    "hit_history.json",
    "item_statuses.json",
    "scanned_items.json",
    "chrome_session.json",
    "site_templates.json",
    "ai_settings.json",
    "ai_call_logs.jsonl",
    "ai_repair_history.jsonl",
    "schedules.json",
    "change_alerts.json",
    "change_alert_states.json",
    "risk_confirmations.json",
    "monitor_log.txt",
    "startup_error.log",
    "self_test_error.log",
}
FORBIDDEN_FILE_PATTERNS = (
    "*.sqlite3",
    "*.db",
    "*.log",
    "diagnostic_log_*.txt",
    "ui_snapshot*.png",
)
REQUIRED_GITIGNORE_PATTERNS = (
    "build/",
    "dist/",
    "build_*/",
    "dist_*/",
    "self_test_runtime/",
    "self_test_runtime_probe/",
    "chrome-profile/",
    "采集结果导出/",
    "*.sqlite3",
    "*.db",
    "*.log",
    "diagnostic_log_*.txt",
    "ui_snapshot*.png",
    "app_settings.json",
    "hit_history.json",
    "item_statuses.json",
    "scanned_items.json",
)


def git_lines(args):
    result = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def is_forbidden_tracked_path(path):
    normalized = path.replace("\\", "/")
    top = normalized.split("/", 1)[0]
    is_nested_path = "/" in normalized
    if is_nested_path and (top in FORBIDDEN_DIR_NAMES or top.startswith(FORBIDDEN_DIR_PREFIXES)):
        return True
    name = Path(normalized).name
    if name in FORBIDDEN_FILE_NAMES:
        return True
    return any(fnmatch.fnmatch(name, pattern) for pattern in FORBIDDEN_FILE_PATTERNS)


def main():
    tracked_paths = git_lines(["ls-files"])
    offenders = [path for path in tracked_paths if is_forbidden_tracked_path(path)]
    ignore_file = Path(".gitignore")
    ignore_text = ignore_file.read_text(encoding="utf-8") if ignore_file.exists() else ""
    missing_patterns = [pattern for pattern in REQUIRED_GITIGNORE_PATTERNS if pattern not in ignore_text]
    if offenders or missing_patterns:
        if offenders:
            print("Tracked generated artifacts:")
            for path in offenders:
                print(f"  - {path}")
        if missing_patterns:
            print("Missing .gitignore patterns:")
            for pattern in missing_patterns:
                print(f"  - {pattern}")
        return 1
    print("Repository hygiene OK: generated runtime/build artifacts are ignored and untracked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
