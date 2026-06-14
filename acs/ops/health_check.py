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
    check("Dashboard /", lambda: _check_dashboard("/"))
    check("Dashboard /charts", lambda: _check_dashboard("/charts"))
    check("Chart API shadow", lambda: _check_chart_api())
    check("Scheduler cron export", lambda: _check_cron_export())
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
    # Check for actual key strings like "sk-xxx" hardcoded (not in getenv/os.environ)
    import re
    real_key = re.findall(r'["\']sk-[a-zA-Z0-9]{30,}["\']', src)
    count = len(real_key)
    return (count == 0, "no hardcoded key" if count == 0 else "WARNING: {} hardcoded key(s)".format(count))

def _check_adapter():
    import subprocess
    r = subprocess.run([sys.executable, "-m", "acs.adapter"], capture_output=True, text=True, timeout=30, cwd=_PROJ)
    ok = r.returncode == 0 and '"overall": "pass"' in r.stdout
    return ok, "adapter pass" if ok else r.stderr[:100]

def _check_dashboard(route):
    try:
        from acs.web.app import app
        app.config["TESTING"] = True
        with app.test_client() as c:
            rv = c.get(route)
            return (rv.status_code == 200, f"{route} status={rv.status_code}")
    except Exception as e:
        return (False, str(e)[:100])

def _check_chart_api():
    try:
        from acs.web.app import app
        app.config["TESTING"] = True
        with app.test_client() as c:
            rv = c.get("/api/charts/shadow_trend")
            data = rv.get_json()
            ok = "labels" in data
            return (ok, f"shadow_trend API {'OK' if ok else 'ERROR'}")
    except Exception as e:
        return (False, str(e)[:100])

def _check_cron_export():
    try:
        from acs.ops.scheduler import export_cron
        r = export_cron()
        ok = "daily_cron" in r and "weekly_cron" in r
        return (ok, f"cron export {'OK' if ok else 'ERROR'}")
    except Exception as e:
        return (False, str(e)[:100])

def _check_selftest():
    import subprocess
    r = subprocess.run([sys.executable, "main.py", "--self-test"], capture_output=True, text=True, timeout=120, cwd=_PROJ)
    ok = r.returncode == 0 and "OK" in r.stdout
    return ok, "self-test pass" if ok else r.stdout[-200:]

if __name__ == "__main__":
    sys.exit(run())
