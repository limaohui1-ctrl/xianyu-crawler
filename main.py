import os
import sys
import traceback
import json
import time

if os.name == "nt":
    import ctypes

    _MUTEX_NAME = "Global\\UniversalWebCollector_SingleInstance_v1"
    _mutex_handle = None

    def acquire_single_instance_lock():
        """Return True if this is the first/only instance. False if another is already running."""
        global _mutex_handle
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.GetLastError.restype = ctypes.c_ulong
        _mutex_handle = kernel32.CreateMutexW(None, True, _MUTEX_NAME)
        if _mutex_handle and kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(_mutex_handle)
            _mutex_handle = None
            return False
        return True

    def release_single_instance_lock():
        """Release the mutex. Safe to call even if lock wasn't acquired."""
        global _mutex_handle
        if _mutex_handle:
            kernel32 = ctypes.windll.kernel32
            kernel32.CloseHandle(_mutex_handle)
            _mutex_handle = None
else:
    def acquire_single_instance_lock():
        return True

    def release_single_instance_lock():
        pass


SELF_TEST_RUNTIME_DIR = "self_test_runtime"


def latest_universal_self_test_status_file():
    return os.path.abspath(os.path.join(SELF_TEST_RUNTIME_DIR, "latest_universal_self_test.json"))


def write_universal_self_test_status(pid, status, runtime_dir, error_log_file="", exit_code=None):
    status_file = latest_universal_self_test_status_file()
    os.makedirs(os.path.dirname(status_file), exist_ok=True)
    payload = {
        "pid": int(pid),
        "status": status,
        "exit_code": exit_code,
        "runtime_dir": os.path.abspath(runtime_dir),
        "error_log_file": os.path.abspath(error_log_file) if error_log_file else "",
        "error_log_present": bool(error_log_file and os.path.exists(error_log_file)),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(status_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def clear_stale_universal_self_test_errors(current_runtime_dir):
    root = os.path.abspath(SELF_TEST_RUNTIME_DIR)
    current_runtime_dir = os.path.abspath(current_runtime_dir)
    if not os.path.isdir(root):
        return
    legacy_error_logs = [
        os.path.join(root, "self_test_error.log"),
        os.path.join(root, "universal", "self_test_error.log"),
    ]
    for error_log in legacy_error_logs:
        if os.path.exists(error_log):
            try:
                os.remove(error_log)
            except OSError:
                pass
    for name in os.listdir(root):
        if not name.startswith("pid-"):
            continue
        candidate = os.path.abspath(os.path.join(root, name))
        if candidate == current_runtime_dir:
            continue
        error_log = os.path.join(candidate, "universal", "self_test_error.log")
        if os.path.exists(error_log):
            try:
                os.remove(error_log)
            except OSError:
                pass


def clear_stale_startup_error(startup_log_file):
    if os.path.exists(startup_log_file):
        os.remove(startup_log_file)

def universal_self_test_env(runtime_dir):
    os.environ["UNIVERSAL_COLLECTOR_SELF_TEST"] = "1"
    os.environ["UNIVERSAL_COLLECTOR_DATA_DIR"] = os.path.join(
        runtime_dir, "universal"
    )
    os.environ["UNIVERSAL_COLLECTOR_DB_FILE"] = os.path.join(
        runtime_dir, "universal", "collector.sqlite3"
    )
    os.environ["UNIVERSAL_COLLECTOR_TEMPLATE_FILE"] = os.path.join(
        runtime_dir, "universal", "site_templates.json"
    )
    os.environ["UNIVERSAL_COLLECTOR_AI_SETTINGS_FILE"] = os.path.join(
        runtime_dir, "universal", "ai_settings.json"
    )
    os.environ["UNIVERSAL_COLLECTOR_AI_CALL_LOG_FILE"] = os.path.join(
        runtime_dir, "universal", "ai_call_logs.jsonl"
    )
    os.environ["UNIVERSAL_COLLECTOR_AI_REPAIR_HISTORY_FILE"] = os.path.join(
        runtime_dir, "universal", "ai_repair_history.jsonl"
    )
    os.environ["UNIVERSAL_COLLECTOR_SCHEDULE_FILE"] = os.path.join(
        runtime_dir, "universal", "schedules.json"
    )
    os.environ["UNIVERSAL_COLLECTOR_CHANGE_ALERT_STATE_FILE"] = os.path.join(
        runtime_dir, "universal", "change_alert_states.json"
    )
    os.environ["UNIVERSAL_COLLECTOR_RISK_CONFIRMATION_FILE"] = os.path.join(
        runtime_dir, "universal", "risk_confirmations.json"
    )
    os.environ["UNIVERSAL_COLLECTOR_STARTUP_LOG_FILE"] = os.path.join(
        runtime_dir, "universal", "startup_error.log"
    )
    os.environ["UNIVERSAL_COLLECTOR_SELF_TEST_ERROR_LOG_FILE"] = os.path.join(
        runtime_dir, "universal", "self_test_error.log"
    )


def xianyu_self_test_env(runtime_dir):
    os.environ["XIANYU_MONITOR_SELF_TEST"] = "1"
    os.environ["XIANYU_MONITOR_SELF_TEST_DIR"] = runtime_dir
    os.environ["XIANYU_MONITOR_SETTINGS_FILE"] = os.path.join(
        runtime_dir, "app_settings.json"
    )
    os.environ["XIANYU_MONITOR_HIT_HISTORY_FILE"] = os.path.join(
        runtime_dir, "hit_history.json"
    )
    os.environ["XIANYU_MONITOR_LOG_FILE"] = os.path.join(
        runtime_dir, "monitor_log.txt"
    )
    os.environ["XIANYU_MONITOR_SMART_RULES_FILE"] = os.path.join(
        runtime_dir, "smart_rules.json"
    )
    os.environ["XIANYU_MONITOR_ITEM_STATUS_FILE"] = os.path.join(
        runtime_dir, "item_statuses.json"
    )
    os.environ["XIANYU_MONITOR_STARTUP_LOG_FILE"] = os.path.join(
        runtime_dir, "startup_error.log"
    )
    os.environ["XIANYU_MONITOR_SELF_TEST_ERROR_LOG_FILE"] = os.path.join(
        runtime_dir, "self_test_error.log"
    )
    os.environ["XIANYU_MONITOR_CHROME_PROFILE_DIR"] = os.path.join(
        runtime_dir, "chrome-profile"
    )
    os.environ["XIANYU_MONITOR_CHROME_SESSION_FILE"] = os.path.join(
        runtime_dir, "chrome_session.json"
    )


def write_error_log(file_path, text=None):
    os.makedirs(os.path.dirname(os.path.abspath(file_path)) or ".", exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(text or traceback.format_exc())


def append_error_log_note(file_path, title, exc):
    try:
        os.makedirs(os.path.dirname(os.path.abspath(file_path)) or ".", exist_ok=True)
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n[{title}]\n")
            f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    except Exception:
        pass


if __name__ == "__main__":
    try:
        if "--self-test" in sys.argv:
            runtime_dir = os.path.abspath(
                os.path.join(SELF_TEST_RUNTIME_DIR, f"pid-{os.getpid()}")
            )
            os.makedirs(runtime_dir, exist_ok=True)
            if "--xianyu" not in sys.argv:
                universal_self_test_env(runtime_dir)
                clear_stale_universal_self_test_errors(runtime_dir)
                write_universal_self_test_status(
                    os.getpid(),
                    "running",
                    runtime_dir,
                    os.environ.get("UNIVERSAL_COLLECTOR_SELF_TEST_ERROR_LOG_FILE", ""),
                )
                from universal_ui import run_universal_self_test

                run_universal_self_test()
                write_universal_self_test_status(
                    os.getpid(),
                    "passed",
                    runtime_dir,
                    os.environ.get("UNIVERSAL_COLLECTOR_SELF_TEST_ERROR_LOG_FILE", ""),
                    exit_code=0,
                )
                sys.exit(0)
            xianyu_self_test_env(runtime_dir)
            from legacy_xianyu import app_core
            from legacy_xianyu import self_test

            self_test.run_self_test(app_core)
        elif "--xianyu" in sys.argv:
            from legacy_xianyu.app_core import ensure_runtime_dirs
            from legacy_xianyu.app_core import main as run_app
            from legacy_xianyu.app_core import STARTUP_LOG_FILE

            ensure_runtime_dirs()
            clear_stale_startup_error(STARTUP_LOG_FILE)
            run_app()
        else:
            if not acquire_single_instance_lock():
                print("通用网站采集中心 已在运行。请勿重复启动。", file=sys.stderr)
                sys.exit(0)
            from universal_core import ensure_runtime_dirs, runtime_startup_log_file
            from universal_ui import run_universal_app

            ensure_runtime_dirs()
            clear_stale_startup_error(runtime_startup_log_file())
            run_universal_app()
    except Exception:
        main_traceback = traceback.format_exc()
        try:
            if "--xianyu" in sys.argv:
                from legacy_xianyu.app_core import SELF_TEST_ERROR_LOG_FILE, STARTUP_LOG_FILE, ensure_runtime_dirs
            else:
                from universal_core import ensure_runtime_dirs, runtime_self_test_error_log_file, runtime_startup_log_file

            ensure_runtime_dirs()
            if "--xianyu" in sys.argv:
                error_log_file = SELF_TEST_ERROR_LOG_FILE if "--self-test" in sys.argv else STARTUP_LOG_FILE
            else:
                error_log_file = runtime_self_test_error_log_file() if "--self-test" in sys.argv else runtime_startup_log_file()
        except Exception as error_log_exc:
            error_log_file = "self_test_error.log" if "--self-test" in sys.argv else "startup_error.log"
            sys.stderr.write(f"启动错误日志路径计算失败，使用当前目录兜底：{error_log_exc}\n")
        write_error_log(error_log_file, main_traceback)
        if "--self-test" in sys.argv and "--xianyu" not in sys.argv:
            try:
                write_universal_self_test_status(
                    os.getpid(),
                    "failed",
                    os.path.abspath(os.path.dirname(os.path.dirname(error_log_file))),
                    error_log_file,
                    exit_code=1,
                )
            except Exception as status_exc:
                append_error_log_note(error_log_file, "self-test-status-write-failed", status_exc)
        raise
