"""Local AI settings encryption and JSONL log storage helpers."""

import base64
import ctypes
import json
import logging
import os
import time
from contextlib import contextmanager
from copy import deepcopy
from ctypes import wintypes

from core_export import clean_text, now_text


SECRET_PREFIX = "dpapi:v1:"
JSONL_TAIL_READ_BYTES = 1024 * 1024
JSONL_LOCK_BYTES = 1


@contextmanager
def jsonl_file_lock(file_path, timeout=5):
    lock_path = f"{file_path}.lock"
    os.makedirs(os.path.dirname(os.path.abspath(lock_path)), exist_ok=True)
    with open(lock_path, "a+b") as lock_file:
        if os.name == "nt":
            import msvcrt

            deadline = time.time() + max(0, float(timeout or 0))
            while True:
                try:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, JSONL_LOCK_BYTES)
                    break
                except OSError:
                    if time.time() >= deadline:
                        raise TimeoutError(f"等待日志文件锁超时：{lock_path}")
                    time.sleep(0.05)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, JSONL_LOCK_BYTES)
        else:
            yield


def tail_jsonl_lines(file_path, limit=200):
    if not limit or limit <= 0:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.readlines()
    file_size = os.path.getsize(file_path)
    read_size = min(file_size, max(JSONL_TAIL_READ_BYTES, int(limit) * 4096))
    with open(file_path, "rb") as f:
        f.seek(max(0, file_size - read_size))
        chunk = f.read(read_size)
    text = chunk.decode("utf-8", errors="ignore")
    lines = text.splitlines()
    if file_size > read_size and lines:
        lines = lines[1:]
    return lines[-int(limit):]


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.c_void_p)]


def _dpapi_transform(data, protect=True):
    if os.name != "nt":
        raise RuntimeError("DPAPI is only available on Windows")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB),
        wintypes.LPCWSTR,
        ctypes.POINTER(_DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DATA_BLOB),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB),
        ctypes.c_void_p,
        ctypes.POINTER(_DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DATA_BLOB),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    in_buffer = ctypes.create_string_buffer(data)
    in_blob = _DATA_BLOB(len(data), ctypes.cast(in_buffer, ctypes.c_void_p))
    out_blob = _DATA_BLOB()
    if protect:
        ok = crypt32.CryptProtectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob))
    else:
        ok = crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob))
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def protect_secret(secret):
    secret = str(secret or "").strip()
    if not secret or secret.startswith(SECRET_PREFIX):
        return secret
    try:
        encrypted = _dpapi_transform(secret.encode("utf-8"), protect=True)
        return SECRET_PREFIX + base64.b64encode(encrypted).decode("ascii")
    except Exception as exc:
        if os.name == "nt":
            raise RuntimeError("API Key 本机加密失败，已拒绝明文保存。") from exc
        return secret


def unprotect_secret(secret):
    secret = str(secret or "").strip()
    if not secret.startswith(SECRET_PREFIX):
        return secret
    try:
        encrypted = base64.b64decode(secret[len(SECRET_PREFIX) :])
        return _dpapi_transform(encrypted, protect=False).decode("utf-8")
    except Exception:
        logging.getLogger(__name__).warning(
            "unprotect_secret DPAPI decryption failed, returning empty string",
            exc_info=True)
        return ""


def _transform_provider_secrets(provider_settings, transformer):
    if not isinstance(provider_settings, dict):
        return provider_settings
    transformed = dict(provider_settings)
    if transformed.get("api_key"):
        transformed["api_key"] = transformer(transformed.get("api_key", ""))
    entries = []
    for entry in transformed.get("api_keys", []) or []:
        if not isinstance(entry, dict):
            continue
        item = dict(entry)
        if item.get("key"):
            item["key"] = transformer(item.get("key", ""))
        entries.append(item)
    transformed["api_keys"] = entries
    return transformed


def encrypt_ai_settings_for_disk(settings):
    encrypted = deepcopy(settings or {})
    for provider_key, provider_settings in list((encrypted.get("providers") or {}).items()):
        encrypted["providers"][provider_key] = _transform_provider_secrets(provider_settings, protect_secret)
    return _transform_provider_secrets(encrypted, protect_secret)


def decrypt_ai_settings_from_disk(settings):
    decrypted = deepcopy(settings or {})
    for provider_key, provider_settings in list((decrypted.get("providers") or {}).items()):
        decrypted["providers"][provider_key] = _transform_provider_secrets(provider_settings, unprotect_secret)
    return _transform_provider_secrets(decrypted, unprotect_secret)


def append_jsonl_entry(file_path, entry):
    payload = dict(entry or {})
    payload.setdefault("time", now_text())
    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
    line = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
    with jsonl_file_lock(file_path):
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
    return payload


def load_jsonl_entries(file_path, limit=200):
    if not os.path.exists(file_path):
        return []
    rows = []
    try:
        safe_limit = int(limit or 0)
    except Exception:
        safe_limit = 200
    with jsonl_file_lock(file_path):
        lines = tail_jsonl_lines(file_path, safe_limit if safe_limit > 0 else 0)
    for line in lines:
        line = str(line).strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    if safe_limit > 0:
        rows = rows[-safe_limit:]
    return list(reversed(rows))


def summarize_ai_call_log_rows(logs):
    groups = {}
    for item in logs or []:
        if not isinstance(item, dict):
            continue
        provider = clean_text(item.get("provider_name") or item.get("provider") or "未知厂商", 120)
        model = clean_text(item.get("model") or "未选择模型", 200)
        key_name = clean_text(item.get("key_name") or "未命名 Key", 120)
        key_mask = clean_text(item.get("key_mask") or "", 120)
        group_key = (provider, model, key_name, key_mask)
        group = groups.setdefault(
            group_key,
            {
                "provider": provider,
                "model": model,
                "key_name": key_name,
                "key_mask": key_mask,
                "key": f"{key_name} {key_mask}".strip(),
                "total_calls": 0,
                "success_count": 0,
                "failure_count": 0,
                "success_rate": "0.0%",
                "avg_duration_ms": 0,
                "auto_switch_count": 0,
                "latest_time": "",
                "latest_error": "",
                "_duration_total": 0,
                "_duration_count": 0,
            },
        )
        group["total_calls"] += 1
        status = clean_text(item.get("status") or "", 40)
        if status in {"成功", "success", "ok", "OK"}:
            group["success_count"] += 1
        else:
            group["failure_count"] += 1
        try:
            duration_ms = int(float(item.get("duration_ms") or 0))
        except Exception:
            duration_ms = 0
        if duration_ms > 0:
            group["_duration_total"] += duration_ms
            group["_duration_count"] += 1
        if item.get("auto_switched_key"):
            group["auto_switch_count"] += 1
        call_time = clean_text(item.get("time") or "", 40)
        if call_time >= group["latest_time"]:
            group["latest_time"] = call_time
            error_text = clean_text(item.get("error") or "", 1000)
            if error_text:
                group["latest_error"] = error_text
        elif not group["latest_error"]:
            group["latest_error"] = clean_text(item.get("error") or "", 1000)

    rows = []
    for group in groups.values():
        total = max(0, int(group["total_calls"]))
        if total:
            group["success_rate"] = f"{group['success_count'] / total * 100:.1f}%"
        if group["_duration_count"]:
            group["avg_duration_ms"] = int(round(group["_duration_total"] / group["_duration_count"]))
        group.pop("_duration_total", None)
        group.pop("_duration_count", None)
        rows.append(group)
    rows.sort(key=lambda item: (item.get("latest_time", ""), item.get("total_calls", 0)), reverse=True)
    return rows


def clear_jsonl_file(file_path):
    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
    with jsonl_file_lock(file_path):
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("")
            f.flush()
    return file_path
