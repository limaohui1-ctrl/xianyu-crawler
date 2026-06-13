"""SQLite persistence and record-change helpers for the collector."""

import hashlib
import json
import logging
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
    try:
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except Exception:
        logging.getLogger(__name__).warning(
            "content_fingerprint JSON serialization failed, falling back to safe values",
            exc_info=True,
        )
        safe_payload = {key: comparable_record_value(value) for key, value in payload.items()}
        text = json.dumps(safe_payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def safe_json(value):
    try:
        return json.dumps(value if value is not None else [], ensure_ascii=False)
    except Exception:
        logging.getLogger(__name__).warning(
            "safe_json serialization failed, returning empty array", exc_info=True)
        return json.dumps([], ensure_ascii=False)


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
            logging.getLogger(__name__).warning(
                "row_to_record JSON parsing failed for key=%s, defaulting to []",
                key, exc_info=True)
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
            logging.getLogger(__name__).warning(
                "row_to_run JSON parsing failed for key=%s, defaulting to empty",
                key, exc_info=True)
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    summary TEXT,
                    tags_json TEXT,
                    sync_enabled INTEGER NOT NULL DEFAULT 0,
                    sync_interval_minutes INTEGER NOT NULL DEFAULT 0,
                    last_synced_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic_id INTEGER NOT NULL,
                    item_type TEXT NOT NULL,
                    title TEXT,
                    summary TEXT,
                    source_url TEXT,
                    source_kind TEXT,
                    source_record_fingerprint TEXT,
                    entity_key TEXT,
                    relation_type TEXT,
                    evidence_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(topic_id) REFERENCES memory_topics(id)
                )
                """
            )
            topic_columns = [row[1] for row in conn.execute("PRAGMA table_info(memory_topics)").fetchall()]
            if "sync_enabled" not in topic_columns:
                conn.execute("ALTER TABLE memory_topics ADD COLUMN sync_enabled INTEGER NOT NULL DEFAULT 0")
            if "sync_interval_minutes" not in topic_columns:
                conn.execute("ALTER TABLE memory_topics ADD COLUMN sync_interval_minutes INTEGER NOT NULL DEFAULT 0")
            if "last_synced_at" not in topic_columns:
                conn.execute("ALTER TABLE memory_topics ADD COLUMN last_synced_at TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_topics_name ON memory_topics(name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_items_topic_id ON memory_items(topic_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_items_entity_key ON memory_items(entity_key)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_items_source_url ON memory_items(source_url)")

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
            logging.getLogger(__name__).warning(
                "run_config JSON parsing failed for run_id=%s", run_id, exc_info=True)
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


    def upsert_memory_topic(self, name, summary="", tags=None):
        name = str(name or "").strip()
        if not name:
            return 0
        tags_json = safe_json(tags or [])
        timestamp = now_text()
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM memory_topics WHERE name = ?", (name,)).fetchone()
            if existing:
                conn.execute(
                    "UPDATE memory_topics SET summary = ?, tags_json = ?, updated_at = ? WHERE id = ?",
                    (summary or "", tags_json, timestamp, int(existing[0])),
                )
                return int(existing[0])
            cursor = conn.execute(
                "INSERT INTO memory_topics (name, summary, tags_json, sync_enabled, sync_interval_minutes, last_synced_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (name, summary or "", tags_json, 1, 60, "", timestamp, timestamp),
            )
            return int(cursor.lastrowid or 0)

    def add_memory_item(self, topic_id, item):
        if not topic_id:
            return 0
        item = item or {}
        timestamp = now_text()
        evidence_json = safe_json(item.get("evidence") or [])
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO memory_items (
                    topic_id, item_type, title, summary, source_url, source_kind,
                    source_record_fingerprint, entity_key, relation_type, evidence_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(topic_id),
                    item.get("item_type", "note"),
                    item.get("title", ""),
                    item.get("summary", ""),
                    item.get("source_url", ""),
                    item.get("source_kind", ""),
                    item.get("source_record_fingerprint", ""),
                    item.get("entity_key", ""),
                    item.get("relation_type", "related"),
                    evidence_json,
                    timestamp,
                    timestamp,
                ),
            )
            return int(cursor.lastrowid or 0)

    def recent_memory_topics(self, limit=100):
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, name, summary, tags_json, sync_enabled, sync_interval_minutes, last_synced_at, created_at, updated_at FROM memory_topics ORDER BY updated_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        results = []
        for row in rows:
            try:
                tags = json.loads(row[3] or "[]")
            except Exception:
                logging.getLogger(__name__).warning(
                    "recent_memory_topics tags JSON parsing failed for topic_id=%s",
                    row[0], exc_info=True)
                tags = []
            results.append({
                "id": int(row[0]),
                "name": row[1] or "",
                "summary": row[2] or "",
                "tags": tags,
                "sync_enabled": bool(row[4]),
                "sync_interval_minutes": int(row[5] or 0),
                "last_synced_at": row[6] or "",
                "created_at": row[7] or "",
                "updated_at": row[8] or "",
            })
        return results

    def memory_items_for_topic(self, topic_id, limit=500):
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, item_type, title, summary, source_url, source_kind,
                       source_record_fingerprint, entity_key, relation_type, evidence_json,
                       created_at, updated_at
                FROM memory_items WHERE topic_id = ? ORDER BY id DESC LIMIT ?
                """,
                (int(topic_id or 0), int(limit)),
            ).fetchall()
        results = []
        for row in rows:
            try:
                evidence = json.loads(row[9] or "[]")
            except Exception:
                evidence = []
            results.append({
                "id": int(row[0]),
                "item_type": row[1] or "",
                "title": row[2] or "",
                "summary": row[3] or "",
                "source_url": row[4] or "",
                "source_kind": row[5] or "",
                "source_record_fingerprint": row[6] or "",
                "entity_key": row[7] or "",
                "relation_type": row[8] or "",
                "evidence": evidence,
                "created_at": row[10] or "",
                "updated_at": row[11] or "",
            })
        return results


    def related_memory_items(self, entity_key="", source_url="", limit=50):
        entity_key = str(entity_key or "").strip()
        source_url = str(source_url or "").strip()
        if not entity_key and not source_url:
            return []
        with self.connect() as conn:
            if entity_key and source_url:
                rows = conn.execute(
                    """
                    SELECT topic_id, item_type, title, summary, source_url, source_kind,
                           source_record_fingerprint, entity_key, relation_type, evidence_json,
                           created_at, updated_at
                    FROM memory_items
                    WHERE entity_key = ? OR source_url = ?
                    ORDER BY updated_at DESC LIMIT ?
                    """,
                    (entity_key, source_url, int(limit)),
                ).fetchall()
            elif entity_key:
                rows = conn.execute(
                    """
                    SELECT topic_id, item_type, title, summary, source_url, source_kind,
                           source_record_fingerprint, entity_key, relation_type, evidence_json,
                           created_at, updated_at
                    FROM memory_items
                    WHERE entity_key = ?
                    ORDER BY updated_at DESC LIMIT ?
                    """,
                    (entity_key, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT topic_id, item_type, title, summary, source_url, source_kind,
                           source_record_fingerprint, entity_key, relation_type, evidence_json,
                           created_at, updated_at
                    FROM memory_items
                    WHERE source_url = ?
                    ORDER BY updated_at DESC LIMIT ?
                    """,
                    (source_url, int(limit)),
                ).fetchall()
        results = []
        for row in rows:
            try:
                evidence = json.loads(row[9] or "[]")
            except Exception:
                evidence = []
            results.append({
                "topic_id": int(row[0]),
                "item_type": row[1] or "",
                "title": row[2] or "",
                "summary": row[3] or "",
                "source_url": row[4] or "",
                "source_kind": row[5] or "",
                "source_record_fingerprint": row[6] or "",
                "entity_key": row[7] or "",
                "relation_type": row[8] or "",
                "evidence": evidence,
                "created_at": row[10] or "",
                "updated_at": row[11] or "",
            })
        return results

    def refresh_memory_topic_summary(self, topic_id):
        if not topic_id:
            return ""
        items = self.memory_items_for_topic(topic_id, 500)
        if not items:
            return ""
        source_count = len({item.get("source_url", "") for item in items if item.get("source_url")})
        entity_count = len({item.get("entity_key", "") for item in items if item.get("entity_key")})
        latest_title = items[0].get("title", "")
        relation_candidates = self.memory_relation_candidates(limit=min(200, len(items) + 20))
        supplement_count = sum(1 for item in relation_candidates if item.get("derived_relation") == "补充候选")
        conflict_count = len(self.memory_conflict_candidates(limit=min(200, len(items) + 20)))
        topic_row = next((topic for topic in self.recent_memory_topics(500) if int(topic.get("id") or 0) == int(topic_id)), {})
        if conflict_count:
            state_text = "有冲突待观察"
        elif supplement_count:
            state_text = "持续补充中"
        elif topic_row.get("sync_enabled"):
            state_text = "自动同步中"
        else:
            state_text = "沉淀中"
        summary = f"状态 {state_text}｜条目 {len(items)} 条｜来源 {source_count} 个｜实体键 {entity_count} 个｜补充候选 {supplement_count} 条｜冲突候选 {conflict_count} 组｜最近：{latest_title}"
        with self.connect() as conn:
            conn.execute(
                "UPDATE memory_topics SET summary = ?, updated_at = ? WHERE id = ?",
                (summary, now_text(), int(topic_id)),
            )
        return summary


    def memory_relation_candidates(self, entity_key="", source_url="", limit=50):
        related = self.related_memory_items(entity_key=entity_key, source_url=source_url, limit=limit)
        candidates = []
        seen = set()
        for item in related:
            key = (item.get("title", ""), item.get("source_url", ""), item.get("entity_key", ""))
            if key in seen:
                continue
            seen.add(key)
            relation = item.get("relation_type") or "相关"
            summary = str(item.get("summary") or "")
            if entity_key and item.get("entity_key") == entity_key:
                relation = "同实体"
            if source_url and item.get("source_url") == source_url:
                relation = "同来源"
            if "价格" in summary and "￥" in summary:
                relation = "补充候选"
            candidates.append({**item, "derived_relation": relation})
        return candidates


    def memory_conflict_candidates(self, entity_key="", limit=50):
        entity_key = str(entity_key or "").strip()
        if not entity_key:
            return []
        related = self.related_memory_items(entity_key=entity_key, limit=limit)
        extracted = []
        for item in related:
            evidence_map = {}
            for pair in item.get("evidence") or []:
                field = str(pair.get("field", "")).strip()
                value = str(pair.get("value", "")).strip()
                if field and value:
                    evidence_map[field] = value
            extracted.append({**item, "evidence_map": evidence_map})
        conflicts = []
        for field in ("price", "author", "title"):
            values = {}
            for item in extracted:
                value = item.get("evidence_map", {}).get(field, "")
                if value:
                    values.setdefault(value, []).append(item)
            if len(values) > 1:
                conflicts.append({
                    "field": field,
                    "variants": [{"value": key, "count": len(rows), "sources": [row.get("source_url", "") for row in rows]} for key, rows in values.items()],
                })
        return conflicts


    def set_memory_topic_sync(self, topic_id, enabled=False, interval_minutes=60):
        if not topic_id:
            return False
        with self.connect() as conn:
            conn.execute(
                "UPDATE memory_topics SET sync_enabled = ?, sync_interval_minutes = ?, updated_at = ? WHERE id = ?",
                (1 if enabled else 0, int(interval_minutes or 0), now_text(), int(topic_id)),
            )
        return True

    def mark_memory_topic_synced(self, topic_id):
        if not topic_id:
            return False
        with self.connect() as conn:
            conn.execute(
                "UPDATE memory_topics SET last_synced_at = ?, updated_at = ? WHERE id = ?",
                (now_text(), now_text(), int(topic_id)),
            )
        return True


    def memory_topic_source_urls(self, topic_id, limit=100):
        if not topic_id:
            return []
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT source_url FROM memory_items WHERE topic_id = ? AND source_url != '' ORDER BY updated_at DESC LIMIT ?",
                (int(topic_id), int(limit)),
            ).fetchall()
        return [row[0] for row in rows if row and row[0]]


    def due_memory_topics(self, now_ts=None, limit=20):
        now_ts = float(now_ts or time.time())
        topics = self.recent_memory_topics(500)
        due = []
        for topic in topics:
            if not topic.get("sync_enabled"):
                continue
            interval_minutes = int(topic.get("sync_interval_minutes") or 0)
            if interval_minutes <= 0:
                continue
            last_synced_at = str(topic.get("last_synced_at") or "").strip()
            if not last_synced_at:
                due.append(topic)
                continue
            try:
                last_ts = time.mktime(time.strptime(last_synced_at, "%Y-%m-%d %H:%M:%S"))
            except Exception:
                due.append(topic)
                continue
            if now_ts - last_ts >= interval_minutes * 60:
                due.append(topic)
        return due[: int(limit)]
