"""Change reports, alerts, memory palace, and run archiving."""

from ui_registry import register

import time

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox, QTableWidgetItem

from universal_core import (
    CollectorDatabase,
    UniversalCollector,
    change_alert_key,
    load_change_alert_states,
    normalize_url,
    save_change_alert_states,
)

@register("generate_change_report")
def generate_change_report(self):
    self.change_report_rows = self.database.change_report(500)
    self.fill_change_report_table(self.change_report_rows)
    if self.change_report_rows:
        self.append_log(f"已生成 {len(self.change_report_rows)} 条网页监控变更记录。")
    else:
        self.append_log("暂未发现变化记录。重复采集同一网址且内容变化后会出现在这里。")

@register("fill_change_report_table")
def fill_change_report_table(self, rows):
    columns = ["监控时间", "网址", "域名", "字段", "旧值", "新值", "标题"]
    self.change_report_table.setRowCount(0)
    for source in rows:
        row = self.change_report_table.rowCount()
        self.change_report_table.insertRow(row)
        for column, key in enumerate(columns):
            value = source.get(key, "")
            item = QTableWidgetItem(str(value))
            item.setToolTip(str(value))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.change_report_table.setItem(row, column, item)

@register("build_change_alert_rows")
def build_change_alert_rows(self, limit=500):
    alerts = []
    for source in self.database.change_report(limit):
        alert_id = change_alert_key(source)
        state = self.change_alert_states.get(alert_id, {})
        alert = {
            "处理状态": state.get("status", "未读"),
            "类型": "变化",
            "监控时间": source.get("监控时间", ""),
            "网址": source.get("网址", ""),
            "字段": source.get("字段", ""),
            "旧值": source.get("旧值", ""),
            "新值": source.get("新值", ""),
            "标题": source.get("标题", ""),
            "域名": source.get("域名", ""),
            "ID": alert_id,
            "状态更新时间": state.get("updated_at", ""),
        }
        alerts.append(alert)
    return alerts

@register("refresh_change_alerts")
def refresh_change_alerts(self, silent=False, notify=False):
    self.change_alert_states = load_change_alert_states()
    self.change_alert_rows = self.build_change_alert_rows(500)
    self.fill_change_alert_table(self.change_alert_rows)
    count = len(self.change_alert_rows)
    if count:
        fields = sorted({item.get("字段", "") for item in self.change_alert_rows if item.get("字段")})
        field_text = "、".join(fields[:5]) or "字段"
        unread = sum(1 for item in self.change_alert_rows if item.get("处理状态") == "未读")
        handled = sum(1 for item in self.change_alert_rows if item.get("处理状态") == "已处理")
        ignored = sum(1 for item in self.change_alert_rows if item.get("处理状态") == "忽略")
        self.change_alert_status_label.setText(
            f"发现 {count} 条变更提醒，未读 {unread}，已处理 {handled}，忽略 {ignored}；涉及：{field_text}"
        )
        if notify and unread:
            latest_unread = next((item for item in self.change_alert_rows if item.get("处理状态") == "未读"), {})
            self.notify_unread_change_alerts(unread, latest_unread)
        if not silent:
            self.append_log(f"已刷新 {count} 条变更提醒。")
    else:
        self.change_alert_status_label.setText("暂无变更提醒；同一网址再次采集且内容变化后会显示。")
        if not silent:
            self.append_log("暂无变更提醒。")
    self.refresh_overview()
    return count

@register("fill_change_alert_table")
def fill_change_alert_table(self, rows):
    columns = ["处理状态", "类型", "监控时间", "网址", "字段", "旧值", "新值", "标题", "域名", "ID"]
    status_filter = self.change_alert_filter_combo.currentText() if hasattr(self, "change_alert_filter_combo") else "全部提醒"
    self.change_alert_table.setRowCount(0)
    for source in rows:
        if status_filter != "全部提醒" and source.get("处理状态") != status_filter:
            continue
        row = self.change_alert_table.rowCount()
        self.change_alert_table.insertRow(row)
        for column, key in enumerate(columns):
            value = source.get(key, "")
            item = QTableWidgetItem(str(value))
            item.setToolTip(str(value))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if key == "处理状态" and value == "未读":
                item.setBackground(Qt.GlobalColor.yellow)
            elif key == "处理状态" and value == "已处理":
                item.setBackground(Qt.GlobalColor.green)
            elif key == "处理状态" and value == "忽略":
                item.setBackground(Qt.GlobalColor.lightGray)
            self.change_alert_table.setItem(row, column, item)

@register("selected_change_alert_id")
def selected_change_alert_id(self):
    selected_rows = sorted({index.row() for index in self.change_alert_table.selectedIndexes()})
    if not selected_rows:
        return ""
    row = selected_rows[0]
    id_item = self.change_alert_table.item(row, 9)
    return id_item.text().strip() if id_item else ""

@register("set_selected_change_alert_status")
def set_selected_change_alert_status(self, status):
    alert_id = self.selected_change_alert_id()
    if not alert_id:
        QMessageBox.information(self, "提示", "请先选择一条变更提醒。")
        return
    self.change_alert_states = load_change_alert_states()
    self.change_alert_states[alert_id] = {
        "status": status,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "note": "",
    }
    self.change_alert_states = save_change_alert_states(self.change_alert_states)
    self.refresh_change_alerts(silent=True)
    self.refresh_overview()
    self.append_log(f"已将变更提醒标记为：{status}。")

@register("run_status_text")
def run_status_text(self, status):
    return {
        "running": "运行中",
        "finished": "已完成",
        "stopped": "已停止",
        "failed": "失败",
        "partial": "部分成功",
    }.get(status or "", status or "")


@register("archive_current_records_to_memory_topic")
def archive_current_records_to_memory_topic(self):
    pass

@register("refresh_memory_palace")
def refresh_memory_palace(self):
    pass

@register("enable_selected_memory_topic_sync")
def enable_selected_memory_topic_sync(self):
    pass

@register("run_memory_topic_sync_by_id")
def run_memory_topic_sync_by_id(self, topic_id):
    pass

@register("run_selected_memory_topic_sync")
def run_selected_memory_topic_sync(self):
    pass

@register("mark_selected_memory_topic_synced")
def mark_selected_memory_topic_synced(self):
    pass

@register("selected_memory_topic_id")
def selected_memory_topic_id(self):
    return None

@register("selected_memory_item")
def selected_memory_item(self):
    return None

@register("relation_label_for_memory_items")
def relation_label_for_memory_items(self, current, related):
    return ""

@register("update_memory_related_view")
def update_memory_related_view(self):
    pass

@register("update_memory_palace_items")
def update_memory_palace_items(self):
    pass
