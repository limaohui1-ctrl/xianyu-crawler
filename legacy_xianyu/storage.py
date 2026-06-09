import json
import os
import time


SCAN_RECORD_HIT_PREFIX = "hit:"


def ensure_parent_dir(file_path):
    parent = os.path.dirname(os.path.abspath(file_path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def atomic_write_json(file_path, data):
    ensure_parent_dir(file_path)
    file_path = os.path.abspath(file_path)
    temp_path = f"{file_path}.tmp.{os.getpid()}.{int(time.time() * 1000)}"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, file_path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def backup_corrupt_file(file_path, reason):
    if not os.path.exists(file_path):
        return None
    backup_path = (
        f"{file_path}.corrupt-{time.strftime('%Y%m%d_%H%M%S')}.{os.getpid()}.bak"
    )
    try:
        os.replace(file_path, backup_path)
        return backup_path
    except Exception:
        return None


class HitStore:
    def __init__(self, file_path):
        self.file_path = file_path
        self.records = []
        self.keys = set()
        self.dirty = False

    def load(self):
        if not os.path.exists(self.file_path):
            self.reset([])
            return []

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            backup_corrupt_file(self.file_path, str(exc))
            self.reset([])
            return []

        if not isinstance(data, list):
            backup_corrupt_file(self.file_path, "JSON type mismatch")
            self.reset([])
            return []

        self.reset(data)
        return list(self.records)

    def reset(self, items):
        self.records = [
            item
            for item in dict.fromkeys(str(item) for item in items if str(item).strip())
            if item.startswith(SCAN_RECORD_HIT_PREFIX)
        ]
        self.keys = set(self.records)
        self.dirty = False

    def hit_record_key(self, scanned_key):
        return f"{SCAN_RECORD_HIT_PREFIX}{scanned_key}"

    def has_seen_hit(self, scanned_key):
        return self.hit_record_key(scanned_key) in self.keys

    def remember_hit(self, scanned_key):
        record_key = self.hit_record_key(scanned_key)
        if record_key in self.keys:
            return False

        self.keys.add(record_key)
        self.records.append(record_key)
        self.dirty = True
        return True

    def clear(self):
        self.reset([])
        self.dirty = True

    def save(self, force=False):
        if not force and not self.dirty:
            return False

        self.records = [
            item
            for item in dict.fromkeys(str(item) for item in self.records)
            if item.startswith(SCAN_RECORD_HIT_PREFIX)
        ]
        self.keys = set(self.records)
        atomic_write_json(self.file_path, self.records)
        self.dirty = False
        return True
