"""AI call log and repair history actions for the universal UI."""

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem

from universal_core import (
    FieldRule,
    clear_ai_call_logs,
    export_table_data,
    load_ai_call_logs,
    load_ai_repair_history,
    summarize_ai_call_logs,
)
from ui_export_utils import selected_export_path


def refresh_ai_call_logs(self):
    logs = load_ai_call_logs(200)
    self.fill_ai_call_log_table(logs)
    self.fill_ai_call_summary_table(summarize_ai_call_logs(logs))

def fill_ai_call_log_table(self, logs):
    self.ai_call_log_table.setRowCount(0)
    for item in logs or []:
        row = self.ai_call_log_table.rowCount()
        self.ai_call_log_table.insertRow(row)
        values = [
            item.get("time", ""),
            item.get("action", ""),
            item.get("status", ""),
            item.get("provider_name") or item.get("provider", ""),
            item.get("model", ""),
            f"{item.get('key_name', '')} {item.get('key_mask', '')}".strip(),
            item.get("duration_ms", ""),
            item.get("auto_switched_key", ""),
            item.get("error", ""),
        ]
        for column, value in enumerate(values):
            self.ai_call_log_table.setItem(row, column, QTableWidgetItem(str(value)))

def refresh_ai_call_summary(self):
    self.fill_ai_call_summary_table(summarize_ai_call_logs())

def fill_ai_call_summary_table(self, rows):
    self.ai_call_summary_table.setRowCount(0)
    for item in rows or []:
        row = self.ai_call_summary_table.rowCount()
        self.ai_call_summary_table.insertRow(row)
        values = [
            item.get("provider", ""),
            item.get("model", ""),
            item.get("key", ""),
            item.get("total_calls", 0),
            item.get("success_count", 0),
            item.get("failure_count", 0),
            item.get("success_rate", "0.0%"),
            item.get("avg_duration_ms", 0),
            item.get("auto_switch_count", 0),
            item.get("latest_error", ""),
        ]
        for column, value in enumerate(values):
            self.ai_call_summary_table.setItem(row, column, QTableWidgetItem(str(value)))

def ai_call_log_table_data(self):
    columns = ["时间", "动作", "状态", "厂商", "模型", "Key", "耗时ms", "自动切换", "错误"]
    rows = []
    for item in load_ai_call_logs(0):
        rows.append(
            [
                item.get("time", ""),
                item.get("action", ""),
                item.get("status", ""),
                item.get("provider_name") or item.get("provider", ""),
                item.get("model", ""),
                f"{item.get('key_name', '')} {item.get('key_mask', '')}".strip(),
                item.get("duration_ms", ""),
                item.get("auto_switched_key", ""),
                item.get("error", ""),
            ]
        )
    return columns, rows

def export_ai_call_logs_to_file(self, file_path):
    columns, rows = self.ai_call_log_table_data()
    if not rows:
        raise RuntimeError("没有可导出的 AI 调用日志。")
    return export_table_data(file_path, columns, rows, sheet_name="AI调用日志")

def ai_call_summary_table_data(self):
    columns = ["厂商", "模型", "Key", "总次数", "成功", "失败", "成功率", "平均耗时ms", "自动切换", "最近时间", "最近错误"]
    rows = []
    for item in summarize_ai_call_logs():
        rows.append(
            [
                item.get("provider", ""),
                item.get("model", ""),
                item.get("key", ""),
                item.get("total_calls", 0),
                item.get("success_count", 0),
                item.get("failure_count", 0),
                item.get("success_rate", "0.0%"),
                item.get("avg_duration_ms", 0),
                item.get("auto_switch_count", 0),
                item.get("latest_time", ""),
                item.get("latest_error", ""),
            ]
        )
    return columns, rows

def export_ai_call_summary_to_file(self, file_path):
    columns, rows = self.ai_call_summary_table_data()
    if not rows:
        raise RuntimeError("没有可导出的 AI 用量汇总。")
    return export_table_data(file_path, columns, rows, sheet_name="AI用量汇总")

def ai_repair_history_table_data(self):
    columns = ["时间", "厂商", "模型", "样本数", "字段数", "改善", "持平", "变差", "平均变化", "失败字段"]
    rows = []
    for item in getattr(self, "ai_repair_history_entries", None) or load_ai_repair_history(0):
        rows.append(
            [
                item.get("time", ""),
                item.get("provider_name") or item.get("provider", ""),
                item.get("model", ""),
                item.get("sample_count", 0),
                item.get("field_count", 0),
                item.get("improved_count", 0),
                item.get("unchanged_count", 0),
                item.get("worse_count", 0),
                item.get("avg_delta", 0),
                "、".join(item.get("failed_fields", []) or []),
            ]
        )
    return columns, rows

def refresh_ai_repair_history(self):
    if not hasattr(self, "ai_repair_history_table"):
        return
    self.ai_repair_history_entries = load_ai_repair_history(0)
    columns, rows = self.ai_repair_history_table_data()
    self.ai_repair_history_table.setRowCount(0)
    for values in rows:
        row = self.ai_repair_history_table.rowCount()
        self.ai_repair_history_table.insertRow(row)
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setToolTip(str(value))
            if column == 7 and str(value) not in {"", "0"}:
                item.setBackground(Qt.GlobalColor.red)
            self.ai_repair_history_table.setItem(row, column, item)

def repair_history_score(self, item):
    if not isinstance(item, dict):
        return -999999
    return (
        int(item.get("improved_count") or 0) * 100
        - int(item.get("worse_count") or 0) * 120
        + float(item.get("avg_delta") or 0)
        + int(item.get("sample_count") or 0)
    )

def selected_ai_repair_history_entry(self):
    entries = getattr(self, "ai_repair_history_entries", None)
    if entries is None:
        entries = load_ai_repair_history(0)
        self.ai_repair_history_entries = entries
    row = self.ai_repair_history_table.currentRow() if hasattr(self, "ai_repair_history_table") else -1
    if row < 0 and hasattr(self, "ai_repair_history_table"):
        selected = self.ai_repair_history_table.selectedIndexes()
        row = selected[0].row() if selected else -1
    if row < 0 or row >= len(entries):
        return None
    return entries[row]

def field_rules_from_history_entry(self, entry):
    rules = []
    for item in (entry or {}).get("field_rules", []) or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("field") or "").strip()
        selector = str(item.get("selector") or "").strip()
        if not name or not selector:
            continue
        rules.append(
            FieldRule(
                name,
                selector,
                str(item.get("attr") or "text"),
                bool(item.get("multiple")),
            )
        )
    return rules

def repair_field_rule_signature(self, rule):
    return {
        "selector": rule.selector,
        "attr": rule.attr,
        "multiple": bool(rule.multiple),
    }

def build_repair_history_diff_rows(self, entry):
    current_rules = {rule.name: rule for rule in self.collect_field_rules_from_table()}
    history_rules = {rule.name: rule for rule in self.field_rules_from_history_entry(entry)}
    names = []
    for name in list(current_rules.keys()) + list(history_rules.keys()):
        if name and name not in names:
            names.append(name)
    rows = []
    for name in names:
        current = current_rules.get(name)
        history = history_rules.get(name)
        if current and not history:
            change = "历史缺少"
        elif history and not current:
            change = "历史新增"
        elif self.repair_field_rule_signature(current) != self.repair_field_rule_signature(history):
            change = "有变化"
        else:
            change = "相同"
        rows.append(
            {
                "change": change,
                "field": name,
                "current_selector": current.selector if current else "",
                "history_selector": history.selector if history else "",
                "current_attr": f"{current.attr}/多条={bool(current.multiple)}" if current else "",
                "history_attr": f"{history.attr}/多条={bool(history.multiple)}" if history else "",
            }
        )
    rows.sort(key=lambda row: (row.get("change") == "相同", row.get("field", "")))
    return rows

def fill_repair_history_diff_table(self, rows):
    if not hasattr(self, "ai_repair_diff_table"):
        return
    self.ai_repair_diff_table.setRowCount(0)
    for diff in rows or []:
        row = self.ai_repair_diff_table.rowCount()
        self.ai_repair_diff_table.insertRow(row)
        values = [
            diff.get("change", ""),
            diff.get("field", ""),
            diff.get("current_selector", ""),
            diff.get("history_selector", ""),
            diff.get("current_attr", ""),
            diff.get("history_attr", ""),
        ]
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setToolTip(str(value))
            if column == 0 and value in {"历史新增", "历史缺少", "有变化"}:
                item.setBackground(Qt.GlobalColor.yellow)
            self.ai_repair_diff_table.setItem(row, column, item)

def compare_ai_repair_history_entry(self, entry):
    if not entry:
        self.current_ai_repair_history_entry = None
        self.fill_repair_history_diff_table([])
        return []
    self.current_ai_repair_history_entry = entry
    rows = self.build_repair_history_diff_rows(entry)
    self.fill_repair_history_diff_table(rows)
    changed = sum(1 for row in rows if row.get("change") != "相同")
    self.append_ai_output(f"AI 修复历史差异对比：{changed} 项不同，{len(rows) - changed} 项相同。")
    return rows

def apply_ai_repair_history_entry(self, entry):
    rules = self.field_rules_from_history_entry(entry)
    if not rules:
        QMessageBox.information(self, "提示", "这条修复历史没有可复用的字段配置。")
        return False
    self.compare_ai_repair_history_entry(entry)
    self.field_table.setRowCount(0)
    for rule in rules:
        self.add_field_row(rule)
    self.latest_preview_rules = rules
    self.show_main_tab("模板库")
    self.append_ai_output(
        f"已复用 AI 修复历史：{entry.get('time', '')}，字段 {len(rules)} 个，平均变化 {entry.get('avg_delta', 0)}。"
    )
    return True

def selected_repair_diff_fields(self):
    if not hasattr(self, "ai_repair_diff_table"):
        return []
    fields = []
    rows = {index.row() for index in self.ai_repair_diff_table.selectedIndexes()}
    current_row = self.ai_repair_diff_table.currentRow()
    if current_row >= 0:
        rows.add(current_row)
    for row in sorted(rows):
        item = self.ai_repair_diff_table.item(row, 1)
        field_name = item.text().strip() if item else ""
        if field_name and field_name not in fields:
            fields.append(field_name)
    return fields

def apply_repair_history_fields(self, entry, field_names):
    history_rules = {rule.name: rule for rule in self.field_rules_from_history_entry(entry)}
    selected_names = [name for name in field_names if name in history_rules]
    if not selected_names:
        if os.environ.get("UNIVERSAL_COLLECTOR_SELF_TEST") != "1":
            QMessageBox.information(self, "提示", "请先选择要套用的字段。")
        return False
    self.compare_ai_repair_history_entry(entry)
    selected_rules = {name: history_rules[name] for name in selected_names}
    merged_rules = []
    used_names = set()
    for current in self.collect_field_rules_from_table():
        if current.name in selected_rules:
            merged_rules.append(selected_rules[current.name])
            used_names.add(current.name)
        else:
            merged_rules.append(current)
    for name in selected_names:
        if name not in used_names:
            merged_rules.append(selected_rules[name])
    self.field_table.setRowCount(0)
    for rule in merged_rules:
        self.add_field_row(rule)
    self.latest_preview_rules = merged_rules
    self.show_main_tab("模板库")
    self.append_ai_output(
        f"已应用 AI 修复历史中的 {len(selected_names)} 个字段：{', '.join(selected_names)}。"
    )
    return True

def apply_best_ai_repair_history(self):
    entries = load_ai_repair_history(0)
    entries = [entry for entry in entries if self.field_rules_from_history_entry(entry)]
    if not entries:
        QMessageBox.information(self, "提示", "没有可复用的 AI 修复历史。")
        return False
    best = max(entries, key=self.repair_history_score)
    return self.apply_ai_repair_history_entry(best)

def apply_selected_ai_repair_history(self):
    entry = self.selected_ai_repair_history_entry()
    if not entry:
        QMessageBox.information(self, "提示", "请先在 AI 修复历史表里选中一条记录。")
        return False
    return self.apply_ai_repair_history_entry(entry)

def compare_selected_ai_repair_history(self):
    entry = self.selected_ai_repair_history_entry()
    if not entry:
        self.fill_repair_history_diff_table([])
        return []
    return self.compare_ai_repair_history_entry(entry)

def apply_selected_ai_repair_fields(self):
    entry = getattr(self, "current_ai_repair_history_entry", None) or self.selected_ai_repair_history_entry()
    if not entry:
        QMessageBox.information(self, "提示", "请先在 AI 修复历史表里选中一条记录。")
        return False
    return self.apply_repair_history_fields(entry, self.selected_repair_diff_fields())

def export_ai_repair_history_to_file(self, file_path):
    columns, rows = self.ai_repair_history_table_data()
    if not rows:
        raise RuntimeError("没有可导出的 AI 修复历史。")
    return export_table_data(file_path, columns, rows, sheet_name="AI修复历史")

def export_ai_call_logs(self):
    columns, rows = self.ai_call_log_table_data()
    if not rows:
        QMessageBox.information(self, "提示", "没有可导出的 AI 调用日志。")
        return
    file_path, selected = QFileDialog.getSaveFileName(
        self,
        "导出 AI 调用日志",
        os.path.join(os.getcwd(), "ai_call_logs.xlsx"),
        "Excel 文件 (*.xlsx);;CSV 文件 (*.csv);;JSON 文件 (*.json)",
    )
    if not file_path:
        return
    file_path = selected_export_path(file_path, selected)
    self.export_ai_call_logs_to_file(file_path)
    self.append_ai_output(f"AI 调用日志已导出：{file_path}")

def export_ai_call_summary(self):
    columns, rows = self.ai_call_summary_table_data()
    if not rows:
        QMessageBox.information(self, "提示", "没有可导出的 AI 用量汇总。")
        return
    file_path, selected = QFileDialog.getSaveFileName(
        self,
        "导出 AI 用量汇总",
        os.path.join(os.getcwd(), "ai_call_summary.xlsx"),
        "Excel 文件 (*.xlsx);;CSV 文件 (*.csv);;JSON 文件 (*.json)",
    )
    if not file_path:
        return
    file_path = selected_export_path(file_path, selected)
    self.export_ai_call_summary_to_file(file_path)
    self.append_ai_output(f"AI 用量汇总已导出：{file_path}")

def export_ai_repair_history(self):
    columns, rows = self.ai_repair_history_table_data()
    if not rows:
        QMessageBox.information(self, "提示", "没有可导出的 AI 修复历史。")
        return
    file_path, selected = QFileDialog.getSaveFileName(
        self,
        "导出 AI 修复历史",
        os.path.join(os.getcwd(), "ai_repair_history.xlsx"),
        "Excel 文件 (*.xlsx);;CSV 文件 (*.csv);;JSON 文件 (*.json)",
    )
    if not file_path:
        return
    file_path = selected_export_path(file_path, selected)
    self.export_ai_repair_history_to_file(file_path)
    self.append_ai_output(f"AI 修复历史已导出：{file_path}")

def clear_ai_call_logs_and_refresh(self):
    clear_ai_call_logs()
    self.refresh_ai_call_logs()
    self.append_ai_output("AI 调用日志已清空。")

def confirm_clear_ai_call_logs(self):
    answer = QMessageBox.question(self, "清空调用日志", "确定清空本机 AI 调用日志吗？")
    if answer == QMessageBox.StandardButton.Yes:
        self.clear_ai_call_logs_and_refresh()
