"""Runtime isolation helpers for the universal UI self-test."""

import os
import time


def safe_self_test_print(message):
    try:
        print(message, flush=True)
    except OSError:
        pass


def make_self_test_stage(stage_log_file):
    def self_test_stage(message):
        with open(stage_log_file, "a", encoding="utf-8") as stage_log:
            stage_log.write(f"{time.strftime('%H:%M:%S')} {message}\n")
        safe_self_test_print(f"[DEBUG] universal self-test: {message}")

    return self_test_stage


def prepare_self_test_runtime(default_paths):
    safe_root = os.path.normcase(os.path.abspath("self_test_runtime"))
    data_dir = os.path.abspath(os.environ.get("UNIVERSAL_COLLECTOR_DATA_DIR", ""))
    legacy_shared_dir = os.path.normcase(os.path.join(os.path.abspath("self_test_runtime"), "universal"))
    if not data_dir or os.path.normcase(data_dir) == legacy_shared_dir:
        runtime_dir = os.path.abspath(os.path.join("self_test_runtime", f"pid-{os.getpid()}"))
        data_dir = os.path.join(runtime_dir, "universal")
        os.environ["UNIVERSAL_COLLECTOR_SELF_TEST"] = "1"
        os.environ["UNIVERSAL_COLLECTOR_DATA_DIR"] = data_dir
        os.environ["UNIVERSAL_COLLECTOR_DB_FILE"] = os.path.join(data_dir, "collector.sqlite3")
        os.environ["UNIVERSAL_COLLECTOR_TEMPLATE_FILE"] = os.path.join(data_dir, "site_templates.json")
        os.environ["UNIVERSAL_COLLECTOR_AI_SETTINGS_FILE"] = os.path.join(data_dir, "ai_settings.json")
        os.environ["UNIVERSAL_COLLECTOR_AI_CALL_LOG_FILE"] = os.path.join(data_dir, "ai_call_logs.jsonl")
        os.environ["UNIVERSAL_COLLECTOR_AI_REPAIR_HISTORY_FILE"] = os.path.join(data_dir, "ai_repair_history.jsonl")
        os.environ["UNIVERSAL_COLLECTOR_SCHEDULE_FILE"] = os.path.join(data_dir, "schedules.json")
        os.environ["UNIVERSAL_COLLECTOR_CHANGE_ALERT_STATE_FILE"] = os.path.join(data_dir, "change_alert_states.json")
        os.environ["UNIVERSAL_COLLECTOR_RISK_CONFIRMATION_FILE"] = os.path.join(data_dir, "risk_confirmations.json")
        os.environ["UNIVERSAL_COLLECTOR_STARTUP_LOG_FILE"] = os.path.join(data_dir, "startup_error.log")
        os.environ["UNIVERSAL_COLLECTOR_SELF_TEST_ERROR_LOG_FILE"] = os.path.join(data_dir, "self_test_error.log")
    if not data_dir or not os.path.normcase(data_dir).startswith(safe_root + os.sep):
        raise AssertionError("通用采集中心自检数据目录未隔离")

    stage_log_file = os.path.join(os.path.abspath("self_test_runtime"), "stage.log")
    self_test_stage = make_self_test_stage(stage_log_file)
    paths = {
        key: os.path.abspath(os.environ.get(env_name, default_value))
        for key, env_name, default_value in default_paths
    }
    for file_path in paths.values():
        if os.path.exists(file_path):
            normalized = os.path.normcase(os.path.abspath(file_path))
            if not normalized.startswith(safe_root + os.sep):
                raise AssertionError(f"自检拒绝删除正式路径：{file_path}")
            try:
                os.remove(file_path)
            except PermissionError:
                stale_path = f"{file_path}.locked-{os.getpid()}.bak"
                try:
                    os.replace(file_path, stale_path)
                except PermissionError:
                    self_test_stage(f"跳过被占用的旧自检文件：{os.path.basename(file_path)}")
    return {
        "safe_root": safe_root,
        "data_dir": data_dir,
        "stage_log_file": stage_log_file,
        "self_test_stage": self_test_stage,
        **paths,
    }
