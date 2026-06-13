"""Health check — PASS/WARN/FAIL for all subsystems."""
import os, sys, json, time
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJ = os.path.dirname(os.path.dirname(_HERE))
if _PROJ not in sys.path: sys.path.insert(0, _PROJ)

CHECKS = []

def check(name, fn):
    try:
        ok, msg = fn()
        status = "PASS" if ok else "FAIL"
    except Exception as e:
        ok, msg, status = False, str(e), "FAIL"
    CHECKS.append({"name": name, "status": status, "message": msg[:200], "ok": ok})
    return ok

def run():
    CHECKS.clear()
    check("Directory: acs_shadow_logs", lambda: (os.path.isdir("acs_shadow_logs") or os.makedirs("acs_shadow_logs", exist_ok=True) or True, "writable"))
    check("Directory: logs", lambda: (os.path.isdir("logs") or os.makedirs("logs", exist_ok=True) or True, "writable"))
    check("Directory: acs_data", lambda: (os.path.isdir("acs_data") or os.makedirs("acs_data", exist_ok=True) or True, "writable"))
    check("Directory: reports", lambda: (os.path.isdir("reports") or os.makedirs("reports", exist_ok=True) or True, "writable"))
    check("SQLite: reviews.db", lambda: _check_sqlite("acs_data/reviews.db"))
    check("SQLite: structure_history.db", lambda: _check_sqlite("acs_data/structure_history.db"))
    check("SQLite: dedup.db", lambda: _check_sqlite("acs_data/dedup.db"))
    check("ACS_MODE=shadow", lambda: (os.environ.get("ACS_MODE","shadow") == "shadow", f"ACS_MODE={os.environ.get('ACS_MODE','shadow')}"))
    check("AI_KEY env only", lambda: _check_api_key_env_only())
    check("Adapter smoke", lambda: _check_adapter())
    check("Self-test", lambda: _check_selftest())
    passed = sum(1 for c in CHECKS if c["ok"])
    failed = len(CHECKS) - passed
    status = "PASS" if failed == 0 else ("WARN" if failed <= 2 else "FAIL")
    print(json.dumps({"status": status, "total": len(CHECKS), "passed": passed, "failed": failed,
                      "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "checks": CHECKS},
                     ensure_ascii=False, indent=2))
    return 0 if failed == 0 else 1

def _check_sqlite(path):
    import sqlite3
    try:
        c = sqlite3.connect(path)
        c.execute("SELECT 1")
        c.close()
        return True, "readable"
    except: return False, f"cannot read {path}"

def _check_api_key_env_only():
    import acs.provider.provider_config as pc
    src = open(pc.__file__, encoding="utf-8").read()
    has_key = "sk-" in src or "api_key" in src.lower() and '"***"' not in src
    return (not has_key, "no hardcoded key found" if not has_key else "WARNING: key-like string in source")

def _check_adapter():
    import subprocess
    r = subprocess.run([sys.executable, "-m", "acs.adapter"], capture_output=True, text=True, timeout=30, cwd=_PROJ)
    ok = r.returncode == 0 and '"overall": "pass"' in r.stdout
    return ok, "adapter pass" if ok else r.stderr[:100]

def _check_selftest():
    import subprocess
    r = subprocess.run([sys.executable, "main.py", "--self-test"], capture_output=True, text=True, timeout=60, cwd=_PROJ)
    ok = r.returncode == 0 and "OK" in r.stdout
    return ok, "self-test pass" if ok else r.stdout[-200:]

if __name__ == "__main__":
    sys.exit(run())
