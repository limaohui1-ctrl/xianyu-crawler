"""SQLite persistence and record-change helpers for the collector."""

import hashlib
import json
import os
import sqlite3

from core_export import clean_text, now_text


def content_fingerprint(record):
    payload = {
        "title": record.get("title", ""),
        "price": record.get("price", ""),
        "published_time": record.get("published_time", ""),
        "author": record.get("author", ""),
        "body": record.get("body", ""),
        "images": record.get("images", []),
        "links": record.get("links", []),
        "tables": record.get("tables", []),
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def safe_json(value):
    return json.dumps(value if value is not None else [], ensure_ascii=False)


def comparable_record_value(value):
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return "" if value is None else str(value)


def row_to_record(row):
    keys = [
        "collected_at",
        "url",
        "domain",
        "template_name",
        "title",
        "price",
        "published_time",
        "author",
        "body",
        "images",
        "links",
        "tables",
        "completeness_score",
        "completeness_label",
        "completeness_missing",
        "fingerprint",
        "changed",
        "run_id",
        "error",
    ]
    record = dict(zip(keys, row))
    for key in ("images", "links", "tables", "completeness_missing"):
        try:
            record[key] = json.loads(record.get(key) or "[]")
        except Exception:
            record[key] = []
    record["changed"] = bool(record.get("changed"))
    record["run_id"] = int(record.get("run_id") or 0)
    record["completeness_score"] = int(record.get("completeness_score") or 0)
    return record


def row_to_run(row):
    keys = [
        "id",
        "started_at",
        "finished_at",
        "status",
        "urls",
        "template_name",
        "ai_provider",
        "model",
        "config",
        "risks",
        "result_count",
        "notes",
    ]
    run = dict(zip(keys, row))
    for key in ("urls", "config", "risks"):
        try:
            run[key] = json.loads(run.get(key) or ("{}" if key == "config" else "[]"))
        except Exception:
            run[key] = {} if key == "config" else []
    run["result_count"] = int(run.get("result_count") or 0)
    return run


def compare_records(previous, latest):
    fields = [
        ("标题", "title"),
        ("价格", "price"),
        ("时间", "published_time"),
        ("作者", "author"),
        ("正文", "body"),
        ("图片", "images"),
        ("链接", "links"),
        ("表格", "tables"),
        ("错误", "error"),
    ]
    changes = []
    for label, key in fields:
        old_value = comparable_record_value(previous.get(key))
        new_value = comparable_record_value(latest.get(key))
        if old_value != new_value:
            changes.append((label, clean_text(old_value, 1200), clean_text(new_value, 1200)))
    return changes


class CollectorDatabase:
    def __init__(self, db_file=None, db_file_provider=None, ensure_runtime_dirs_func=None):
        self._db_file_provider = db_file_provider
        self._ensure_runtime_dirs = ensure_runtime_dirs_func
        self.db_file = db_file or self._runtime_db_file()
        self._ensure_dirs()
        self.init_db()

    def _runtime_db_file(self):
        if self._db_file_provider:
            return self._db_file_provider()
        return os.environ.get("UNIVERSAL_COLLECTOR_DB_FILE", os.path.join(os.getcwd(), "collector.sqlite3"))

    def _ensure_dirs(self):
        if self._ensure_runtime_dirs:
            self._ensure_runtime_dirs()
        else:
            os.makedirs(os.path.dirname(os.path.abspath(self.db_file)), exist_ok=True)

    def connect(self):
        conn = sqlite3.connect(self.db_file, timeout=30)
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def init_db(self):
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    collected_at TEXT NOT NULL,
                    url TEXT NOT NULL,
                    domain TEXT,
                    template_name TEXT,
                    title TEXT,
                    price TEXT,
                    published_time TEXT,
                    author TEXT,
                    body TEXT,
                    images_json TEXT,
                    links_json TEXT,
                    tables_json TEXT,
                    completeness_score INTEGER NOT NULL DEFAULT 0,
                    completeness_label TEXT,
                    completeness_missing_json TEXT,
                    fingerprint TEXT NOT NULL,
                    changed INTEGER NOT NULL DEFAULT 0,
                    run_id INTEGER NOT NULL DEFAULT 0,
                    error TEXT
                )
                """
            )
            columns = [row[1] for row in conn.execute("PRAGMA table_info(records)").fetchall()]
            if "run_id" not in columns:
                conn.execute("ALTER TABLE records ADD COLUMN run_id INTEGER NOT NULL DEFAULT 0")
            if "completeness_score" not in columns:
                conn.execute("ALTER TABLE records ADD COLUMN completeness_score INTEGER NOT NULL DEFAULT 0")
            if "completeness_label" not in columns:
                conn.execute("ALTER TABLE records ADD COLUMN completeness_label TEXT")
            if "completeness_missing_json" not in columns:
                conn.execute("ALTER TABLE records ADD COLUMN completeness_missing_json TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_records_url ON records(url)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_records_domain ON records(domain)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_records_fingerprint ON records(fingerprint)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_records_run_id ON records(run_id)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT,
                    urls_json TEXT,
                    template_name TEXT,
                    ai_provider TEXT,
                    model TEXT,
                    config_json TEXT,
                    risks_json TEXT,
                    result_count INTEGER NOT NULL DEFAULT 0,
                    notes TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at)")

    def latest_for_url(self, url):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT fingerprint FROM records WHERE url = ? ORDER BY id DESC LIMIT 1",
                (url,),
            ).fetchone()
        return row[0] if row else ""

    def save_record(self, record, skip_unchanged=False):
        fingerprint = record.get("fingerprint") or content_fingerprint(record)
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT fingerprint FROM records WHERE url = ? ORDER BY id DESC LIMIT 1",
                (record.get("url", ""),),
            ).fetchone()
            previous = row[0] if row else ""
            changed = bool(previous and previous != fingerprint)
            if skip_unchanged and previous == fingerprint:
                record["fingerprint"] = fingerprint
                record["changed"] = False
                record["duplicate"] = True
                return record
            conn.execute(
                """
                INSERT INTO records (
                    collected_at, url, domain, template_name, title, price,
                    published_time, author, body, images_json, links_json,
                    tables_json, completeness_score, completeness_label,
                    completeness_missing_json, fingerprint, changed, run_id, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.get("collected_at", now_text()),
                    record.get("url", ""),
                    record.get("domain", ""),
                    record.get("template_name", ""),
                    record.get("title", ""),
                    record.get("price", ""),
                    record.get("published_time", ""),
                    record.get("author", ""),
                    record.get("body", ""),
                    safe_json(record.get("images", [])),
                    safe_json(record.get("links", [])),
                    safe_json(record.get("tables", [])),
                    int(record.get("completeness_score") or 0),
                    record.get("completeness_label", ""),
                    safe_json(record.get("completeness_missing", [])),
                    fingerprint,
                    1 if changed else 0,
                    int(record.get("run_id") or 0),
                    record.get("error", ""),
                ),
            )
        record["fingerprint"] = fingerprint
        record["changed"] = changed
        record["duplicate"] = False
        return record

    def start_run(self, config, risks=None):
        config = config or {}
        urls = config.get("urls", [])
        started_at = now_text()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO runs (
                    started_at, finished_at, status, urls_json, template_name,
                    ai_provider, model, config_json, risks_json, result_count, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    started_at,
                    "",
                    "running",
                    safe_json(urls),
                    config.get("template_name", ""),
                    config.get("ai_provider", ""),
                    config.get("model", ""),
                    json.dumps(config, ensure_ascii=False),
                    json.dumps(risks or [], ensure_ascii=False),
                    0,
                    config.get("notes", ""),
                ),
            )
            run_id = cursor.lastrowid
        return run_id

    def finish_run(self, run_id, status="finished", result_count=0, notes=""):
        if not run_id:
            return
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE runs
                SET finished_at = ?, status = ?, result_count = ?, notes = ?
                WHERE id = ?
                """,
                (now_text(), status, int(result_count or 0), notes, int(run_id)),
            )

    def update_run_config(self, run_id, config):
        if not run_id:
            return
        with self.connect() as conn:
            conn.execute(
                "UPDATE runs SET config_json = ? WHERE id = ?",
                (json.dumps(config or {}, ensure_ascii=False), int(run_id)),
            )

    def run_config(self, run_id):
        if not run_id:
            return {}
        with self.connect() as conn:
            row = conn.execute(
                "SELECT config_json FROM runs WHERE id = ?",
                (int(run_id),),
            ).fetchone()
        if not row:
            return {}
        try:
            return json.loads(row[0] or "{}")
        except Exception:
            return {}

    def recent_runs(self, limit=100):
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, started_at, finished_at, status, urls_json, template_name,
                       ai_provider, model, config_json, risks_json, result_count, notes
                FROM runs ORDER BY id DESC LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [row_to_run(row) for row in rows]

    def recent_records(self, limit=200):
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT collected_at, url, domain, template_name, title, price,
                       published_time, author, body, images_json, links_json,
                       tables_json, completeness_score, completeness_label,
                       completeness_missing_json, fingerprint, changed, run_id, error
                FROM records ORDER BY id DESC LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [row_to_record(row) for row in rows]

    def records_for_run(self, run_id, limit=500):
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT collected_at, url, domain, template_name, title, price,
                       published_time, author, body, images_json, links_json,
                       tables_json, completeness_score, completeness_label,
                       completeness_missing_json, fingerprint, changed, run_id, error
                FROM records WHERE run_id = ? ORDER BY id DESC LIMIT ?
                """,
                (int(run_id or 0), int(limit)),
            ).fetchall()
        return [row_to_record(row) for row in rows]

    def records_for_url(self, url, limit=2):
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT collected_at, url, domain, template_name, title, price,
                       published_time, author, body, images_json, links_json,
                       tables_json, completeness_score, completeness_label,
                       completeness_missing_json, fingerprint, changed, run_id, error
                FROM records WHERE url = ? ORDER BY id DESC LIMIT ?
                """,
                (url, int(limit)),
            ).fetchall()
        return [row_to_record(row) for row in rows]

    def changed_urls(self, limit=200):
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT url, MAX(collected_at) AS last_seen
                FROM records
                WHERE changed = 1
                GROUP BY url
                ORDER BY last_seen DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [row[0] for row in rows]

    def change_report(self, limit=200):
        rows = []
        for url in self.changed_urls(limit):
            records = self.records_for_url(url, limit=2)
            if len(records) < 2:
                continue
            latest, previous = records[0], records[1]
            for field_name, old_value, new_value in compare_records(previous, latest):
                rows.append(
                    {
                        "监控时间": latest.get("collected_at", ""),
                        "网址": latest.get("url", ""),
                        "域名": latest.get("domain", ""),
                        "字段": field_name,
                        "旧值": old_value,
                        "新值": new_value,
                        "标题": latest.get("title", ""),
                    }
                )
        return rows
