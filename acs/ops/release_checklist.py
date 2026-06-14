"""Release checklist — verify all safety and quality gates."""
import os, sys, json, time, subprocess

CHECKS = []

def ck(name, ok, msg=""):
    CHECKS.append({"name": name, "status": "PASS" if ok else "FAIL", "message": msg, "ok": ok})
    return ok

def run():
    _PROJ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    CHECKS.clear()
    ck("Adapter", _run([sys.executable, "-m", "acs.adapter"], _PROJ))
    ck("Self-test", _run([sys.executable, "main.py", "--self-test"], _PROJ))
    ck("Pytest", _run_pytest(_PROJ))
    ck("Dashboard starts", _check_flask(_PROJ))
    ck("Health check", _run([sys.executable, "-m", "acs.ops.health_check"], _PROJ))
    ck(".env/.env.smoke not tracked", not os.path.exists(".env") or
        subprocess.run(["git", "check-ignore", ".env"], capture_output=True, text=True, cwd=_PROJ).returncode == 0)
    ck("API Key not in source", _check_no_key_in_source(_PROJ))
    ck("ACS_MODE=shadow default", os.environ.get("ACS_MODE", "shadow") == "shadow")
    ck("ACS_MODE=on not default", os.environ.get("ACS_MODE", "shadow") != "on")
    ck("Backup dry-run", _run([sys.executable, "-m", "acs.ops.backup_manager", "--dry-run"], _PROJ))
    ck("Retention dry-run", _run([sys.executable, "-m", "acs.ops.data_retention", "--dry-run"], _PROJ))
    passed = sum(1 for c in CHECKS if c["ok"])
    failed = len(CHECKS) - passed
    status = "PASS" if failed == 0 else "FAIL"
    result = {"status": status, "total": len(CHECKS), "passed": passed, "failed": failed,
              "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "checks": CHECKS}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if failed > 0:
        print("\n=== FAILED ===")
        for c in CHECKS:
            if not c["ok"]: print(f"  FAIL: {c['name']} - {c['message']}")
    return 0 if failed == 0 else 1

def _run(cmd, cwd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=cwd)
        return r.returncode == 0
    except: return False

def _run_pytest(cwd):
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q", "-k", "not test_live_get"],
                          capture_output=True, text=True, timeout=120, cwd=cwd)
        return "passed" in r.stdout.lower() and "failed" not in r.stdout.lower()
    except: return False

def _check_flask(cwd):
    try:
        from acs.web.app import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            r = client.get("/")
            return r.status_code == 200
    except: return False

def _check_no_key_in_source(cwd):
    import glob as g
    for f in g.glob(os.path.join(cwd, "acs/**/*.py"), recursive=True):
        try:
            with open(f, encoding="utf-8") as fh:
                src = fh.read()
            if "sk-" in src and "os.environ" not in src and "getenv" not in src and "API_KEY" not in src:
                return False
        except Exception:  # file may be binary or unreadable — skip
            pass
    return True

if __name__ == "__main__":
    sys.exit(run())
