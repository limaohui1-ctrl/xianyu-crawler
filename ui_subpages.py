"""Subpage link scanning, selection, and application."""

from ui_registry import register

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox, QTableWidgetItem

import json
from universal_core import compact_text, normalize_url
from core_urls import normalize_url

from universal_core import UniversalCollector

@register("scan_subpage_links_for_current_url")
def scan_subpage_links_for_current_url(self):
    url = self.first_target_url()
    if not url:
        return
    try:
        links = UniversalCollector(logger=self.append_ai_output).scan_subpage_links(
            url,
            use_browser=self.use_browser_checkbox.isChecked(),
            scroll_times=self.scroll_times_input.value(),
            keep_login_state=self.keep_login_checkbox.isChecked(),
            limit=120,
        )
    except Exception as exc:
        QMessageBox.warning(self, "扫描失败", str(exc))
        self.append_ai_output(f"扫描子页面失败：{exc}")
        return
    self.show_subpage_link_candidates(links)
    selected_count = len(self.selected_urls_from_subpage_table())
    self.append_ai_output(f"已扫描 {len(links)} 个候选链接，默认选中 {selected_count} 个同站详情候选。")

@register("show_subpage_link_candidates")
def show_subpage_link_candidates(self, links):
    self.subpage_link_table.setRowCount(0)
    for link in links:
        row = self.subpage_link_table.rowCount()
        self.subpage_link_table.insertRow(row)
        checked = QTableWidgetItem()
        checked.setCheckState(Qt.CheckState.Checked if link.get("selected") else Qt.CheckState.Unchecked)
        self.subpage_link_table.setItem(row, 0, checked)
        values = [
            link.get("type", ""),
            link.get("text", ""),
            link.get("url", ""),
            link.get("reason", ""),
            link.get("score", ""),
        ]
        for offset, value in enumerate(values, start=1):
            item = QTableWidgetItem(str(value))
            item.setToolTip(str(value))
            if offset in (1, 4, 5):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.subpage_link_table.setItem(row, offset, item)

@register("selected_urls_from_subpage_table")
def selected_urls_from_subpage_table(self):
    urls = []
    for row in range(self.subpage_link_table.rowCount()):
        enabled = self.subpage_link_table.item(row, 0)
        if enabled and enabled.checkState() != Qt.CheckState.Checked:
            continue
        url_item = self.subpage_link_table.item(row, 3)
        url = normalize_url(url_item.text() if url_item else "")
        if url and url not in urls:
            urls.append(url)
    return urls

@register("apply_selected_subpage_links")
def apply_selected_subpage_links(self):
    urls = self.selected_urls_from_subpage_table()
    self.selected_subpage_urls = urls
    self.subpage_limit_input.setValue(min(max(len(urls), 0), self.subpage_limit_input.maximum()))
    self.subpage_checkbox.setChecked(bool(urls))
    if urls:
        self.append_ai_output(f"已应用 {len(urls)} 个子页面。开始采集时会优先深抓这些链接。")
    else:
        self.append_ai_output("已清空手动选择的子页面链接，采集将按原设置自动判断。")
