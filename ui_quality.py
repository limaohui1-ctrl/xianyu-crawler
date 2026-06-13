"""Quality and low-completeness retry helpers for the universal UI."""

from ui_registry import register

from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QHeaderView, QLabel, QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout

import os
from universal_core import compact_text, export_table_data, normalize_url
from core_export import export_table_data
from core_urls import normalize_url

@register("refresh_low_quality_retry_report_summary")
def refresh_low_quality_retry_report_summary(self):
    if hasattr(self, "simple_retry_report_label"):
        self.simple_retry_report_label.setText(self.retry_report_summary_text())

@register("retry_report_table_data")
def retry_report_table_data(self):
    columns = [
        "网址",
        "标题",
        "重抓原因",
        "重抓前完整度",
        "重抓后完整度",
        "提升分数",
        "多抓正文字数",
        "新增图片",
        "新增链接",
        "新增表格",
        "补到资料",
        "仍缺资料",
    ]
    rows = []
    for row in getattr(self, "low_quality_retry_report_rows", []) or []:
        rows.append(
            [
                row.get("url", ""),
                row.get("title", ""),
                row.get("reason", ""),
                row.get("before", 0),
                row.get("after", 0),
                row.get("delta", 0),
                row.get("body_delta", 0),
                row.get("image_delta", 0),
                row.get("link_delta", 0),
                row.get("table_delta", 0),
                row.get("captured", ""),
                row.get("still_missing", ""),
            ]
        )
    return columns, rows

@register("simple_export_retry_report")
def simple_export_retry_report(self):
    columns, rows = self.retry_report_table_data()
    if not rows:
        self.simple_information("提示", "还没有重抓效果报告。请先使用“重抓低完整度”。")
        return False
    file_path = self.simple_export_filename("重抓效果报告")
    try:
        export_table_data(file_path, columns, rows, sheet_name="重抓效果报告")
    except Exception as exc:
        QMessageBox.warning(self, "保存失败", str(exc))
        return False
    self.simple_progress_label.setText(f"已导出重抓效果报告：{file_path}")
    self.simple_status_label.setText("重抓效果报告已保存为 Excel")
    self.last_simple_retry_report_export_path = file_path
    self.last_simple_export_path = file_path
    self.refresh_simple_recent_area()
    self.simple_information("保存成功", f"已保存：\n{file_path}")
    return True

@register("low_quality_records")
def low_quality_records(self, records=None, limit=100):
    source_records = list(records if records is not None else (self.records or self.database.recent_records(limit)))
    weak_records = []
    required_missing = {"图片", "价格", "表格/规格"}
    seen_urls = set()
    for record in source_records:
        if not isinstance(record, dict):
            continue
        self.ensure_record_completeness(record)
        url = normalize_url(record.get("url", ""))
        if not url or url in seen_urls:
            continue
        score = int(record.get("completeness_score") or 0)
        missing = set(record.get("completeness_missing", []) or [])
        if score < 60 or missing.intersection(required_missing):
            weak_records.append(record)
            seen_urls.add(url)
    return weak_records

@register("low_quality_urls")
def low_quality_urls(self, records=None, limit=100):
    urls = []
    for record in self.low_quality_records(records, limit):
        url = normalize_url(record.get("url", ""))
        if url and url not in urls:
            urls.append(url)
    return urls

@register("low_quality_retry_queue")
def low_quality_retry_queue(self, records=None, limit=100):
    queue_rows = []
    for record in self.low_quality_records(records, limit):
        url = normalize_url(record.get("url", ""))
        if not url:
            continue
        queue_rows.append(
            {
                "enabled": True,
                "url": url,
                "title": compact_text(record.get("title") or "(无标题)", 80),
                "completeness": record.get("completeness_label", ""),
                "missing": "、".join(record.get("completeness_missing", []) or []),
            }
        )
    return queue_rows

@register("low_quality_retry_baseline_for_urls")
def low_quality_retry_baseline_for_urls(self, urls, records=None):
    selected_urls = {normalize_url(url) for url in urls or [] if normalize_url(url)}
    if not selected_urls:
        return {}
    baseline = {}
    for record in self.low_quality_records(records):
        url = normalize_url(record.get("url", ""))
        if not url or url not in selected_urls:
            continue
        self.ensure_record_completeness(record)
        baseline[url] = {
            "url": url,
            "title": record.get("title") or "(无标题)",
            "score": int(record.get("completeness_score") or 0),
            "label": record.get("completeness_label", ""),
            "missing": list(record.get("completeness_missing", []) or []),
        }
    return baseline

@register("retry_baseline_snapshot_for_urls")
def retry_baseline_snapshot_for_urls(self, urls, records=None, reason="重抓"):
    selected_urls = {normalize_url(url) for url in urls or [] if normalize_url(url)}
    if not selected_urls:
        return {}
    source_records = list(records if records is not None else getattr(self, "records", []))
    baseline = {}
    for record in source_records:
        if not isinstance(record, dict):
            continue
        url = normalize_url(record.get("url", ""))
        if not url or url not in selected_urls:
            continue
        self.ensure_record_completeness(record)
        baseline[url] = {
            "url": url,
            "title": record.get("title") or "(无标题)",
            "score": int(record.get("completeness_score") or 0),
            "label": record.get("completeness_label", ""),
            "missing": list(record.get("completeness_missing", []) or []),
            "body_length": len(compact_text(record.get("body", ""), 100000)),
            "images": len(record.get("images", []) or []),
            "links": len(record.get("links", []) or []),
            "tables": len(record.get("tables", []) or []),
            "reason": reason,
        }
    for url in selected_urls:
        baseline.setdefault(
            url,
            {
                "url": url,
                "title": "(无标题)",
                "score": 0,
                "label": "0% 偏少",
                "missing": [],
                "body_length": 0,
                "images": 0,
                "links": 0,
                "tables": 0,
                "reason": reason,
            },
        )
    return baseline

@register("start_retry_comparison_tracking")
def start_retry_comparison_tracking(self, urls, reason="重抓"):
    self.low_quality_retry_baseline = self.retry_baseline_snapshot_for_urls(urls, reason=reason)
    self.low_quality_retry_active = True
    self.low_quality_retry_report_rows = []
    self.refresh_low_quality_retry_report_summary()

@register("confirm_low_quality_retry_queue")
def confirm_low_quality_retry_queue(self, queue_rows):
    self.last_low_quality_retry_queue = [dict(row) for row in queue_rows or []]
    if not queue_rows:
        return []
    if os.environ.get("UNIVERSAL_COLLECTOR_SELF_TEST") == "1":
        return [row.get("url", "") for row in queue_rows if row.get("enabled", True)]

@register("simple_retry_low_quality_items")
def simple_retry_low_quality_items(self):
    if self.worker:
        self.simple_status_label.setText("正在采集，请先等待当前任务结束")
        self.simple_information("提示", "正在采集，请先等待当前任务结束。")
        return False
    queue_rows = self.low_quality_retry_queue()
    urls = self.confirm_low_quality_retry_queue(queue_rows)
    urls = [normalize_url(url) for url in urls]
    urls = [url for index, url in enumerate(urls) if url and url not in urls[:index]]
    if not urls:
        self.simple_status_label.setText("当前没有低完整度结果需要重抓")
        self.simple_information("提示", "当前没有低完整度结果需要重抓。")
        return False
    self.start_retry_comparison_tracking(urls, reason="低完整度重抓")
    complete_index = self.simple_depth_combo.findData("complete") if hasattr(self, "simple_depth_combo") else -1
    if complete_index >= 0:
        self.simple_depth_combo.setCurrentIndex(complete_index)
    depth_config = self.simple_collect_depth_config()
    self.simple_select_default_template()
    self.use_browser_checkbox.setChecked(True)
    self.page_limit_input.setValue(depth_config["page_limit"])
    self.scroll_times_input.setValue(max(depth_config["scroll_times"], self.scroll_times_input.value()))
    self.delay_input.setValue(max(1, self.delay_input.value()))
    self.simple_url_input.setPlainText("\n".join(urls))
    self.sync_simple_inputs_to_background()
    self.simple_status_label.setText(f"正在用完整模式重抓 {len(urls)} 条低完整度结果")
    self.simple_progress_label.setText("后台：低完整度结果会用完整深度重新采集，重点补图片、价格和规格")
    self.append_log(f"普通首页已准备重抓 {len(urls)} 条低完整度结果。")
    self.start_collecting(
        skip_confirmation=True,
        runtime_overrides={
            "scrape_subpages": True,
            "subpage_limit": depth_config["subpage_limit"],
            "selected_subpage_urls": [],
            "simple_auto_subpages": True,
            "simple_collect_depth": depth_config["label"],
            "skip_unchanged": False,
        },
    )
    return True

@register("retry_report_captured_fields")
def retry_report_captured_fields(self, before_missing, after_missing):
    before_set = set(before_missing or [])
    after_set = set(after_missing or [])
    captured = sorted(before_set - after_set)
    still_missing = sorted(after_set)
    return captured, still_missing

@register("retry_report_summary_text")
def retry_report_summary_text(self):
    rows = list(getattr(self, "low_quality_retry_report_rows", []) or [])
    if not rows:
        return "重抓效果：暂无"
    total_delta = sum(int(row.get("delta") or 0) for row in rows)
    average_delta = int(total_delta / len(rows)) if rows else 0
    improved = sum(1 for row in rows if int(row.get("delta") or 0) > 0)
    image_delta = sum(int(row.get("image_delta") or 0) for row in rows)
    link_delta = sum(int(row.get("link_delta") or 0) for row in rows)
    table_delta = sum(int(row.get("table_delta") or 0) for row in rows)
    body_delta = sum(int(row.get("body_delta") or 0) for row in rows)
    captured_values = []
    still_missing_values = []
    for row in rows:
        captured_values.extend(row.get("captured_fields", []) or [])
        still_missing_values.extend(row.get("still_missing_fields", []) or [])
    captured_unique = list(dict.fromkeys(captured_values))[:4]
    still_missing_unique = list(dict.fromkeys(still_missing_values))[:4]
    captured_text = "、".join(captured_unique) if captured_unique else "暂无新增"
    still_missing_text = "、".join(still_missing_unique) if still_missing_unique else "无"
    return (
        f"重抓效果：已回收 {len(rows)} 条，提升 {improved} 条，平均 {average_delta:+d} 分；"
        f"多抓正文 {body_delta:+d} 字，图片 {image_delta:+d}，链接 {link_delta:+d}，表格 {table_delta:+d}；"
        f"补到 {captured_text}；仍缺 {still_missing_text}"
    )

@register("update_low_quality_retry_report")
def update_low_quality_retry_report(self, record):
    if not getattr(self, "low_quality_retry_active", False):
        return
    url = normalize_url(record.get("url", ""))
    baseline = getattr(self, "low_quality_retry_baseline", {}).get(url)
    if not baseline:
        return
    self.ensure_record_completeness(record)
    before_score = int(baseline.get("score") or 0)
    after_score = int(record.get("completeness_score") or 0)
    captured, still_missing = self.retry_report_captured_fields(
        baseline.get("missing", []),
        record.get("completeness_missing", []),
    )
    body_delta = len(compact_text(record.get("body", ""), 100000)) - int(baseline.get("body_length") or 0)
    image_delta = len(record.get("images", []) or []) - int(baseline.get("images") or 0)
    link_delta = len(record.get("links", []) or []) - int(baseline.get("links") or 0)
    table_delta = len(record.get("tables", []) or []) - int(baseline.get("tables") or 0)
    row = {
        "url": url,
        "title": record.get("title") or baseline.get("title") or "(无标题)",
        "reason": baseline.get("reason", "重抓"),
        "before": before_score,
        "after": after_score,
        "delta": after_score - before_score,
        "body_delta": body_delta,
        "image_delta": image_delta,
        "link_delta": link_delta,
        "table_delta": table_delta,
        "captured": "、".join(captured) if captured else "暂无新增",
        "still_missing": "、".join(still_missing) if still_missing else "资料较完整",
        "captured_fields": captured,
        "still_missing_fields": still_missing,
    }
    rows = [item for item in getattr(self, "low_quality_retry_report_rows", []) if item.get("url") != url]
    rows.append(row)
    self.low_quality_retry_report_rows = rows
    self.refresh_low_quality_retry_report_summary()
