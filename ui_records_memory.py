"""Record management, auto-memory, and completeness helpers."""

from ui_registry import register

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QTableWidgetItem

from universal_core import FIELD_HEADERS, compact_text, normalize_url

@register("auto_memory_topic_name_for_record")
def auto_memory_topic_name_for_record(self, record):
    title = str(record.get("title") or "").strip()
    domain = str(record.get("domain") or "").strip()
    if title:
        return title[:80]
    if domain:
        return f"{domain} 主题"
    return "未命名主题"

@register("auto_memory_entity_key_for_record")
def auto_memory_entity_key_for_record(self, record):
    title = str(record.get("title") or "").strip().lower()
    price = str(record.get("price") or "").strip()
    author = str(record.get("author") or "").strip().lower()
    domain = str(record.get("domain") or "").strip().lower()
    base = title or author or domain or str(record.get("url") or "").strip().lower()
    if price:
        return f"{base}::{price}"[:160]
    return base[:160]

@register("auto_archive_record_to_memory")
def auto_archive_record_to_memory(self, record):
    if not isinstance(record, dict):
        return 0
    topic_name = self.auto_memory_topic_name_for_record(record)
    topic_summary = f"自动同步来源：{record.get('domain', '') or '未知'}"
    topic_id = self.database.upsert_memory_topic(topic_name, summary=topic_summary, tags=[record.get("domain", "")])
    body = str(record.get("body") or "").strip()
    summary = body[:160] if body else str(record.get("price") or record.get("author") or record.get("url") or "")[:160]
    source_url = record.get("url", "")
    source_kind = record.get("source_kind", "web_page")
    relation_type = "来源引用"
    if source_url.lower().endswith(".pdf"):
        source_kind = "pdf_document"
        relation_type = "文档引用"
    entity_key = self.auto_memory_entity_key_for_record(record)
    evidence = [
        {"field": "title", "value": record.get("title", "")},
        {"field": "price", "value": record.get("price", "")},
        {"field": "author", "value": record.get("author", "")},
        {"field": "domain", "value": record.get("domain", "")},
    ]
    item_id = self.database.add_memory_item(
        topic_id,
        {
            "item_type": "record",
            "title": str(record.get("title") or source_url or "未命名记录")[:120],
            "summary": summary,
            "source_url": source_url,
            "source_kind": source_kind,
            "source_record_fingerprint": record.get("fingerprint", ""),
            "entity_key": entity_key,
            "relation_type": relation_type,
            "evidence": evidence,
        },
    )
    self.database.refresh_memory_topic_summary(topic_id)
    return item_id

@register("add_record")
def add_record(self, record):
    if getattr(self, "current_run_strategy_label", "") and not record.get("simple_collect_depth"):
        record["simple_collect_depth"] = self.current_run_strategy_label
    self.ensure_record_completeness(record)
    self.records.append(record)
    record_index = len(self.records) - 1
    self.add_record_to_table(self.result_table, record, "current", len(self.records) - 1)
    if hasattr(self, "simple_result_table"):
        merged_to_parent = False
        if getattr(self, "simple_merge_subpage_results", False):
            parent_index = self.simple_find_parent_record_index(record)
            if parent_index >= 0:
                parent_record = self.records[parent_index]
                merged_to_parent = self.simple_merge_subpage_into_parent(parent_record, record)
                if merged_to_parent:
                    self.ensure_record_completeness(parent_record, force=True)
                    self.update_low_quality_retry_report(parent_record)
                    for row in range(self.simple_result_table.rowCount()):
                        marker = self.simple_result_table.item(row, 0)
                        if marker and marker.data(Qt.ItemDataRole.UserRole + 1) == parent_index:
                            self.simple_refresh_result_row(row, parent_record, parent_index)
                            self.simple_result_table.selectRow(row)
                            break
                    self.append_log(f"已把详情页资料合并到主结果：{compact_text(parent_record.get('title') or parent_record.get('url'), 80)}")
        if not merged_to_parent:
            self.add_record_to_simple_table(record, record_index)
            if self.simple_result_table.rowCount() == 1:
                self.simple_result_table.selectRow(0)
        self.update_simple_result_preview()
        self.refresh_simple_field_table()
        self.simple_status_label.setText(f"已采到 {len(self.records)} 条结果")
        self.set_simple_flow_step("导出")
        self.refresh_simple_result_summary()
    self.refresh_result_status_summary()
    self.fill_result_quality_table()
    self.refresh_new_user_flow_status("export")
    self.update_queue_result_summary_for_record(record)
    self.update_low_quality_retry_report(record)
    self.auto_archive_record_to_memory(record)

@register("record_status_text")
def record_status_text(self, record):
    if record.get("error"):
        return "错误"
    if record.get("duplicate"):
        return "重复"
    if record.get("changed"):
        return "变化"
    return "新增"

@register("style_record_row")
def style_record_row(self, table, row, record):
    status = self.record_status_text(record)
    palette = {
        "错误": ("#fff1f0", "#a8071a"),
        "变化": ("#fffbe6", "#ad6800"),
        "重复": ("#f5f5f5", "#595959"),
        "新增": ("#f6ffed", "#237804"),
    }
    background, foreground = palette.get(status, ("#ffffff", "#262626"))
    status_column = FIELD_HEADERS.index("是否变化") if "是否变化" in FIELD_HEADERS else FIELD_HEADERS.index("变化")
    error_column = FIELD_HEADERS.index("错误")
    important_columns = {
        status_column,
        error_column,
    }
    for column in range(table.columnCount()):
        item = table.item(row, column)
        if not item:
            continue
        item.setBackground(QColor(background))
        if column in important_columns:
            item.setForeground(QColor(foreground))
            if status == "错误" and column == error_column:
                item.setForeground(QColor("#a8071a"))

@register("refresh_result_status_summary")
def refresh_result_status_summary(self):
    if not hasattr(self, "result_status_label"):
        return
    if not self.records:
        self.result_status_label.setText("结果状态：等待采集")
        if hasattr(self, "result_export_hint_label"):
            self.result_export_hint_label.setText("导出引导：采到结果后可导出 Excel 或复制到 Sheets")
        return
    counts = {"新增": 0, "变化": 0, "重复": 0, "错误": 0}
    for record in self.records:
        counts[self.record_status_text(record)] = counts.get(self.record_status_text(record), 0) + 1
    parts = [f"{name} {count}" for name, count in counts.items() if count]
    self.result_status_label.setText(f"结果状态：共 {len(self.records)} 条｜" + "｜".join(parts))
    if hasattr(self, "result_export_hint_label"):
        image_count = sum(len(record.get("images", []) or []) for record in self.records)
        image_text = f"；发现 {image_count} 张图片，可到高级设置下载图片" if image_count else ""
        self.result_export_hint_label.setText(
            f"导出引导：已可导出 Excel，或复制到 Sheets；选中行可打开原网页{image_text}"
        )

@register("add_record_to_table")
def add_record_to_table(self, table, record, source="current", record_index=None):
    self.ensure_record_completeness(record)
    row = table.rowCount()
    table.insertRow(row)
    status_text = self.record_status_text(record)
    values = [
        record.get("collected_at", ""),
        record.get("url", ""),
        record.get("domain", ""),
        record.get("template_name", ""),
        record.get("title", ""),
        record.get("price", ""),
        record.get("published_time", ""),
        record.get("author", ""),
        record.get("body", ""),
        str(len(record.get("images", []) or [])),
        str(len(record.get("links", []) or [])),
        str(len(record.get("tables", []) or [])),
        record.get("completeness_label", ""),
        "、".join(record.get("completeness_missing", []) or []),
        record.get("fingerprint", "")[:16],
        status_text,
        record.get("error", ""),
    ]
    for column, value in enumerate(values):
        item = QTableWidgetItem(str(value))
        item.setToolTip(str(value))
        if column == 0:
            item.setData(Qt.ItemDataRole.UserRole, source)
            item.setData(
                Qt.ItemDataRole.UserRole + 1,
                record_index if record_index is not None else row,
            )
        table.setItem(row, column, item)
    self.style_record_row(table, row, record)

@register("selected_record_from_table")
def selected_record_from_table(self, table):
    selected = table.selectedIndexes()
    if not selected:
        return None
    row = selected[0].row()
    marker = table.item(row, 0)
    if marker:
        source = marker.data(Qt.ItemDataRole.UserRole)
        index = marker.data(Qt.ItemDataRole.UserRole + 1)
        if source == "current" and isinstance(index, int) and 0 <= index < len(self.records):
            return self.records[index]
        if source == "history" and isinstance(index, int) and 0 <= index < len(self.history_records):
            return self.history_records[index]
    url_item = table.item(row, 1)
    url = url_item.text() if url_item else ""
    for record in self.records + self.history_records + self.database.recent_records(500):
        if record.get("url") == url:
            return record
    return None

@register("update_current_detail")
def update_current_detail(self):
    source = self.sender()
    if source is getattr(self, "simple_result_table", None):
        record = self.selected_record_from_table(self.simple_result_table)
    else:
        record = self.selected_record_from_table(self.result_table)
    self.update_detail_panel(record)

@register("update_history_detail")
def update_history_detail(self):
    record = self.selected_record_from_table(self.history_table)
    if not record:
        self.history_detail_title_label.setText("未选择历史记录")
        self.history_detail_body_output.clear()
        self.history_detail_link_table.setRowCount(0)
        self.history_detail_table_view.setRowCount(0)
        self.history_detail_table_view.setColumnCount(0)
        return
    self.history_detail_title_label.setText(
        f"{record.get('title', '') or '(无标题)'}\n{record.get('url', '')}"
    )
    self.history_detail_body_output.setPlainText(record.get("body", ""))
    self.fill_link_table(self.history_detail_link_table, record.get("links", []) or [])
    self.fill_table_widget(self.history_detail_table_view, record.get("tables", []) or [])

@register("update_detail_panel")
def update_detail_panel(self, record):
    if not record:
        self.detail_title_label.setText("未选择结果")
        self.detail_url_label.setText("")
        self.detail_meta_label.setText("")
        self.detail_body_output.clear()
        self.clear_image_preview()
        self.detail_link_table.setRowCount(0)
        self.detail_table_view.setRowCount(0)
        self.detail_table_view.setColumnCount(0)
        return
    self.detail_title_label.setText(record.get("title", "") or "(无标题)")
    self.detail_url_label.setText(record.get("url", ""))
    meta_parts = [
        f"域名：{record.get('domain', '')}",
        f"模板：{record.get('template_name', '')}",
        f"价格：{record.get('price', '')}",
        f"时间：{record.get('published_time', '')}",
        f"作者：{record.get('author', '')}",
        f"状态：{self.record_status_text(record)}",
    ]
    self.detail_meta_label.setText(" | ".join(part for part in meta_parts if part.split("：", 1)[1]))
    self.detail_body_output.setPlainText(record.get("body", ""))
    self.update_image_preview(record.get("images", []) or [])
    self.update_link_preview(record.get("links", []) or [])
    self.update_table_preview(record.get("tables", []) or [])
