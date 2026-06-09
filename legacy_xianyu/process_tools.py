import ctypes
import json
import os
import re
import subprocess
import sys


APP_MUTEX_NAME = "Global\\XianyuMonitorSingleInstance"
APP_WAKE_EVENT_NAME = "Global\\XianyuMonitorWakeEvent"
CREATE_NO_WINDOW = 0x08000000


class SingleInstanceLock:
    def __init__(self, name=APP_MUTEX_NAME):
        self.name = name
        self.handle = None
        self.already_running = False

    def acquire(self):
        if os.name != "nt":
            return True

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        self.handle = kernel32.CreateMutexW(None, False, self.name)
        last_error = ctypes.get_last_error()
        self.already_running = last_error == 183
        return bool(self.handle) and not self.already_running

    def release(self):
        if os.name != "nt" or not self.handle:
            return

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_bool
        kernel32.CloseHandle(self.handle)
        self.handle = None


def current_pid():
    return os.getpid()


def is_python_monitor_command(command_line):
    if not command_line:
        return False

    normalized = command_line.replace("/", "\\").lower()
    main_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py").lower()
    return "python" in normalized and main_path in normalized


def expected_exe_names():
    return {"闲鱼监测软件.exe", "xianyu_monitor.exe"}


def is_packaged_monitor_process(name, executable_path, command_line):
    lowered_name = os.path.basename(str(name or "")).lower()
    if lowered_name not in {value.lower() for value in expected_exe_names()}:
        return False

    app_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.abspath(sys.executable),
        os.path.join(app_dir, "闲鱼监测软件.exe"),
        os.path.join(app_dir, "dist", "闲鱼监测软件", "闲鱼监测软件.exe"),
    ]
    normalized_path = os.path.normcase(os.path.abspath(str(executable_path or "")))
    if normalized_path and any(
        normalized_path == os.path.normcase(os.path.abspath(candidate))
        for candidate in candidates
        if candidate
    ):
        return True

    normalized_command = str(command_line or "").replace("/", "\\").lower()
    normalized_app_dir = os.path.normcase(app_dir).replace("/", "\\").lower()
    return normalized_app_dir in normalized_command and lowered_name in normalized_command


def is_monitor_process_record(item):
    command_line = str(item.get("CommandLine", ""))
    executable_path = str(item.get("ExecutablePath", ""))
    name = str(item.get("Name", ""))
    return is_python_monitor_command(command_line) or is_packaged_monitor_process(
        name,
        executable_path,
        command_line,
    )


def monitor_processes():
    if os.name != "nt":
        return []

    command = [
        "powershell.exe",
        "-NoProfile",
        "-Command",
        (
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            "Get-CimInstance Win32_Process | "
            "Where-Object { "
            "(($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') -and $_.CommandLine -like '*main.py*') "
            "-or ($_.Name -eq '闲鱼监测软件.exe') "
            "} | "
            "Select-Object ProcessId,Name,CreationDate,CommandLine,ExecutablePath | ConvertTo-Json -Compress"
        ),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
            timeout=6,
            check=False,
        )
    except Exception:
        return []

    if completed.returncode != 0 or not completed.stdout.strip():
        return []

    try:
        data = json.loads(completed.stdout)
    except Exception:
        return []

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []

    processes = []
    for item in data:
        command_line = str(item.get("CommandLine", ""))
        if not is_monitor_process_record(item):
            continue
        try:
            pid = int(item.get("ProcessId", 0))
        except Exception:
            continue
        if pid <= 0:
            continue
        processes.append(
            {
                "pid": pid,
                "name": str(item.get("Name", "")),
                "created_at": format_creation_date(item.get("CreationDate", "")),
                "command_line": command_line,
                "executable_path": str(item.get("ExecutablePath", "")),
                "is_current": pid == current_pid(),
            }
        )
    return sorted(processes, key=lambda item: item["pid"])


def format_creation_date(value):
    text = str(value or "")
    match = re.search(r"/Date\((\d+)\)/", text)
    if match:
        try:
            import datetime

            seconds = int(match.group(1)) / 1000
            return datetime.datetime.fromtimestamp(seconds).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return text
    return text.replace("T", " ").split(".")[0]


def other_monitor_processes():
    return [item for item in monitor_processes() if not item["is_current"]]


def process_record_by_pid(pid):
    if os.name != "nt":
        return None
    command = [
        "powershell.exe",
        "-NoProfile",
        "-Command",
        (
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            f"Get-CimInstance Win32_Process -Filter \"ProcessId={int(pid)}\" | "
            "Select-Object ProcessId,Name,CreationDate,CommandLine,ExecutablePath | ConvertTo-Json -Compress"
        ),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
            timeout=4,
            check=False,
        )
        if completed.returncode != 0 or not completed.stdout.strip():
            return None
        data = json.loads(completed.stdout)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def terminate_process(pid, expected_process=None):
    if pid == current_pid():
        return False, "不能结束当前正在操作的窗口。"

    try:
        pid = int(pid)
    except Exception:
        return False, "PID 无效。"

    latest = process_record_by_pid(pid)
    if not latest:
        return False, "进程已不存在。"
    if not is_monitor_process_record(latest):
        return False, "PID 已不再是本软件实例，已取消结束。"
    if expected_process:
        expected_name = str(expected_process.get("name", ""))
        if expected_name and str(latest.get("Name", "")) != expected_name:
            return False, "PID 身份已变化，已取消结束。"

    try:
        subprocess.run(
            ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
            timeout=6,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "taskkill 执行失败").strip()
        return False, message
    except Exception as exc:
        return False, str(exc)

    return True, ""


def is_owned_debug_chrome(pid, profile_dir, port=9222):
    record = process_record_by_pid(pid)
    if not record:
        return False
    name = os.path.basename(str(record.get("Name", ""))).lower()
    command_line = str(record.get("CommandLine", "")).lower()
    expected_profile = os.path.normcase(os.path.abspath(profile_dir)).lower()
    return (
        name == "chrome.exe"
        and f"--remote-debugging-port={port}" in command_line
        and expected_profile in os.path.normcase(command_line).lower()
    )


def terminate_owned_chrome(pid, profile_dir):
    try:
        pid = int(pid)
    except Exception:
        return False, "Chrome PID 无效。"
    if not is_owned_debug_chrome(pid, profile_dir):
        return False, "Chrome PID 不匹配本软件启动参数，已跳过。"
    try:
        subprocess.run(
            ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
            timeout=6,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        return False, (exc.stderr or exc.stdout or "taskkill 执行失败").strip()
    except Exception as exc:
        return False, str(exc)
    return True, ""


def pythonw_executable():
    executable = sys.executable
    if os.path.basename(executable).lower() == "python.exe":
        candidate = os.path.join(os.path.dirname(executable), "pythonw.exe")
        if os.path.exists(candidate):
            return candidate
    return executable


def signal_existing_window():
    if os.name != "nt":
        return False

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenEventW.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.OpenEventW.restype = ctypes.c_void_p
    kernel32.SetEvent.argtypes = [ctypes.c_void_p]
    kernel32.SetEvent.restype = ctypes.c_bool
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_bool

    event_modify_state = 0x0002
    handle = kernel32.OpenEventW(event_modify_state, False, APP_WAKE_EVENT_NAME)
    if not handle:
        return False
    try:
        return bool(kernel32.SetEvent(handle))
    finally:
        kernel32.CloseHandle(handle)
