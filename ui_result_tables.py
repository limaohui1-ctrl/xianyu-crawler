"""Result table, completeness display, and simple row helpers."""

from ui_registry import register

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QHeaderView, QProgressBar, QTableWidget, QTableWidgetItem

import json


from universal_core import FIELD_HEADERS, compact_text, normalize_url


@register("create_result_table")
def create_result_table(self):
    table = QTableWidget(0, len(FIELD_HEADERS))
    table.setHorizontalHeaderLabels(FIELD_HEADERS)
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    for index in range(2, len(FIELD_HEADERS)):
        table.horizontalHeader().setSectionResizeMode(index, QHeaderView.ResizeMode.ResizeToContents)
    table.verticalHeader().setVisible(False)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    return table

@register("create_simple_result_table")
def create_simple_result_table(self):
    table = QTableWidget(0, 7)
    table.setHorizontalHeaderLabels(["状态", "标题", "内容", "网址", "图片", "完整度", "错误"])
    table.verticalHeader().setVisible(False)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
    table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
    table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
    table.setColumnWidth(5, 138)
    table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
    return table

@register("completeness_score_color")
def completeness_score_color(self, score):
    score = int(score or 0)
    if score >= 85:
        return "#16a34a"
    if score >= 60:
        return "#d97706"
    return "#dc2626"

@register("completeness_bar_widget")
def completeness_bar_widget(self, record):
    self.ensure_record_completeness(record)
    score = max(0, min(100, int(record.get("completeness_score") or 0)))
    label = record.get("completeness_label") or f"{score}%"
    missing = "、".join(record.get("completeness_missing", []) or [])
    progress = QProgressBar()
    progress.setRange(0, 100)
    progress.setValue(score)
    progress.setFormat(label)
    progress.setTextVisible(True)
    color = self.completeness_score_color(score)
    progress.setToolTip(f"{label}" + (f"\n缺少：{missing}" if missing else "\n资料较完整"))
    progress.setStyleSheet(
        f"""
            border: 1px solid #cbd5e1;
            border-radius: 4px;
            background: #f8fafc;
            text-align: center;
            color: #111827;
            font-weight: 600;
            min-height: 18px;
        }}
            background: {color};
            border-radius: 3px;
        }}
        """
    )
    return progress

@register("simple_missing_hint")
def simple_missing_hint(self, record):
    self.ensure_record_completeness(record)
    missing = record.get("completeness_missing", []) or []
    if not missing:
        return "资料较完整"
    hint = "缺少：" + "、".join(missing[:4])
    if len(missing) > 4:
        hint += f"等 {len(missing)} 项"
    return hint

@register("add_record_to_simple_table")
def add_record_to_simple_table(self, record, record_index=None):
    if not hasattr(self, "simple_result_table"):
        return
    self.ensure_record_completeness(record)
    row = self.simple_result_table.rowCount()
    self.simple_result_table.insertRow(row)
    body_preview = compact_text(record.get("body", ""), 160)
    if not body_preview and record.get("tables"):
        body_preview = "已抓到表格"
    if not body_preview and record.get("links"):
        body_preview = f"已抓到 {len(record.get('links') or [])} 个链接"
    values = [
        self.record_status_text(record),
        record.get("title", "") or "(无标题)",
        body_preview,
        record.get("url", ""),
        str(len(record.get("images", []) or [])),
        record.get("completeness_label", ""),
        record.get("error", ""),
    ]
    for column, value in enumerate(values):
        item = QTableWidgetItem(str(value))
        item.setToolTip(str(value))
        if column == 1:
            item.setToolTip(f"{value}\n{self.simple_missing_hint(record)}")
        if column == 5:
            item.setToolTip(self.simple_missing_hint(record))
        if column == 0:
            item.setData(Qt.ItemDataRole.UserRole, "current")
            item.setData(
                Qt.ItemDataRole.UserRole + 1,
                record_index if record_index is not None else row,
            )
        self.simple_result_table.setItem(row, column, item)
    self.simple_result_table.setCellWidget(row, 5, self.completeness_bar_widget(record))
    self.style_simple_record_row(row, record)

@register("simple_refresh_result_row")
def simple_refresh_result_row(self, row, record, record_index=None):
    if not hasattr(self, "simple_result_table") or row < 0 or row >= self.simple_result_table.rowCount():
        return
    self.ensure_record_completeness(record)
    body_preview = compact_text(record.get("body", ""), 160)
    if not body_preview and record.get("tables"):
        body_preview = "已抓到表格"
    if not body_preview and record.get("links"):
        body_preview = f"已抓到 {len(record.get('links') or [])} 个链接"
    values = [
        self.record_status_text(record),
        record.get("title", "") or "(无标题)",
        body_preview,
        record.get("url", ""),
        str(len(record.get("images", []) or [])),
        record.get("completeness_label", ""),
        record.get("error", ""),
    ]
    for column, value in enumerate(values):
        item = self.simple_result_table.item(row, column)
        if item is None:
            item = QTableWidgetItem()
            self.simple_result_table.setItem(row, column, item)
        item.setText(str(value))
        item.setToolTip(str(value))
        if column == 1:
            item.setToolTip(f"{value}\n{self.simple_missing_hint(record)}")
        if column == 5:
            item.setToolTip(self.simple_missing_hint(record))
        if column == 0:
            item.setData(Qt.ItemDataRole.UserRole, "current")
            item.setData(Qt.ItemDataRole.UserRole + 1, record_index if record_index is not None else row)
    self.simple_result_table.setCellWidget(row, 5, self.completeness_bar_widget(record))
    self.style_simple_record_row(row, record)

@register("simple_record_link_urls")
def simple_record_link_urls(self, record):
    urls = []
    for link in record.get("links", []) or []:
        raw_url = link.get("url", "") if isinstance(link, dict) else str(link)
        normalized = normalize_url(raw_url, record.get("url", ""))
        if normalized and normalized not in urls:
            urls.append(normalized)
    return urls

@register("simple_find_parent_record_index")
def simple_find_parent_record_index(self, record):
    target_url = normalize_url(record.get("url", ""))
    if not target_url:
        return -1
    cached = getattr(self, "simple_subpage_parent_map", {}).get(target_url)
    if isinstance(cached, int) and 0 <= cached < len(self.records):
        return cached
    for index, source in enumerate(self.records):
        if source is record:
            continue
        if target_url in self.simple_record_link_urls(source):
            self.simple_subpage_parent_map[target_url] = index
            return index
    return -1

@register("simple_unique_list")
def simple_unique_list(self, items):
    result = []
    seen = set()
    for item in items or []:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, dict) else str(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result

@register("simple_merge_subpage_into_parent")
def simple_merge_subpage_into_parent(self, parent, child):
    changed = False
    if child.get("body") and child.get("body") not in (parent.get("body") or ""):
        parent["body"] = compact_text(((parent.get("body") or "") + "\n\n" + child.get("body", "")).strip(), 5000)
        changed = True
    for scalar_key in ("price", "published_time", "author"):
        if not parent.get(scalar_key) and child.get(scalar_key):
            parent[scalar_key] = child.get(scalar_key)
            changed = True
    for list_key in ("images", "links", "tables"):
        before_count = len(parent.get(list_key, []) or [])
        parent[list_key] = self.simple_unique_list((parent.get(list_key, []) or []) + (child.get(list_key, []) or []))
        if len(parent.get(list_key, []) or []) != before_count:
            changed = True
    if changed:
        parent["simple_detail_enriched"] = True
        parent["simple_detail_urls"] = self.simple_unique_list((parent.get("simple_detail_urls", []) or []) + [child.get("url", "")])
    return changed

@register("style_simple_record_row")
def style_simple_record_row(self, row, record):
    if not hasattr(self, "simple_result_table"):
        return
    status = self.record_status_text(record)
    self.ensure_record_completeness(record)
    score = int(record.get("completeness_score") or 0)
    palette = {
        "错误": ("#fff1f0", "#a8071a"),
        "变化": ("#fffbe6", "#ad6800"),
        "重复": ("#f5f5f5", "#595959"),
        "新增": ("#f6ffed", "#237804"),
    }
    background, foreground = palette.get(status, ("#ffffff", "#262626"))
    if status == "新增":
        if score < 60:
            background, foreground = ("#fff1f0", "#a8071a")
        elif score < 85:
            background, foreground = ("#fffbe6", "#ad6800")
    for column in range(self.simple_result_table.columnCount()):
        item = self.simple_result_table.item(row, column)
        if not item:
            continue
        item.setBackground(QColor(background))
        if column == 0:
            item.setForeground(QColor(foreground))
            item.setToolTip(f"{status}｜{record.get('completeness_label', '')}\n{self.simple_missing_hint(record)}")
