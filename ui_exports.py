"""Export and spreadsheet-copy actions for the universal UI."""

from ui_registry import register

from PyQt6.QtGui import QClipboard
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

import json
from universal_core import export_records, export_table_data, records_to_tsv
from core_export import export_records, export_table_data, records_to_tsv
from ui_export_utils import export_default_path, selected_export_path

@register("export_current_results")
def export_current_results(self):
    self.export_records_dialog(self.records, "导出本次采集结果")

@register("copy_records_to_sheets")
def copy_records_to_sheets(self, records, label="采集结果"):
    if not records:
        QMessageBox.information(self, "提示", "没有可复制的数据。")
        return False
    copied_text = records_to_tsv(records)
    clipboard = QApplication.clipboard()
    clipboard.clear()
    clipboard.setText(copied_text, mode=QClipboard.Mode.Clipboard)
    self.last_clipboard_text = copied_text
    QApplication.processEvents()
    self.append_log(f"已复制 {label}：{len(records)} 条，可直接粘贴到 Google Sheets 或 Excel。")
    if label == "本次采集结果" and hasattr(self, "result_export_hint_label"):
        self.result_export_hint_label.setText(f"导出引导：已复制 {len(records)} 条，可粘贴到 Google Sheets 或 Excel")
    return True

@register("copy_current_results_to_sheets")
def copy_current_results_to_sheets(self):
    return self.copy_records_to_sheets(self.records, "本次采集结果")

@register("export_history_results")
def export_history_results(self):
    self.export_records_dialog(self.database.recent_records(10000), "导出历史数据")

@register("copy_history_results_to_sheets")
def copy_history_results_to_sheets(self):
    self.copy_records_to_sheets(self.database.recent_records(10000), "历史采集结果")

@register("export_change_alerts")
def export_change_alerts(self):
    if not self.change_alert_rows:
        self.refresh_change_alerts(silent=True)
    if not self.change_alert_rows:
        QMessageBox.information(self, "提示", "没有可导出的变更提醒。")
        return
    file_path, selected = QFileDialog.getSaveFileName(
        self,
        "导出变更提醒",
        export_default_path("网页监控变更提醒.xlsx"),
        "Excel 文件 (*.xlsx);;CSV 文件 (*.csv);;JSON 文件 (*.json)",
    )
    if not file_path:
        return
    file_path = selected_export_path(file_path, selected)
    try:
        self.export_change_alerts_to_file(file_path)
    except Exception as exc:
        QMessageBox.warning(self, "导出失败", str(exc))
        return
    QMessageBox.information(self, "导出成功", f"已导出：\n{file_path}")

@register("export_change_report")
def export_change_report(self):
    if not self.change_report_rows:
        self.generate_change_report()
    if not self.change_report_rows:
        QMessageBox.information(self, "提示", "没有可导出的变更报告。")
        return
    columns = ["监控时间", "网址", "域名", "字段", "旧值", "新值", "标题"]
    rows = [[item.get(column, "") for column in columns] for item in self.change_report_rows]
    file_path, selected = QFileDialog.getSaveFileName(
        self,
        "导出变更报告",
        export_default_path("网页监控变更报告.xlsx"),
        "Excel 文件 (*.xlsx);;CSV 文件 (*.csv);;JSON 文件 (*.json)",
    )
    if not file_path:
        return
    file_path = selected_export_path(file_path, selected)
    try:
        export_table_data(file_path, columns, rows, sheet_name="变更报告")
    except Exception as exc:
        QMessageBox.warning(self, "导出失败", str(exc))
        return
    QMessageBox.information(self, "导出成功", f"已导出：\n{file_path}")

@register("export_change_alerts_to_file")
def export_change_alerts_to_file(self, file_path):
    if not self.change_alert_rows:
        self.refresh_change_alerts(silent=True)
    columns = ["处理状态", "类型", "监控时间", "网址", "字段", "旧值", "新值", "标题", "域名", "ID", "状态更新时间"]
    rows = [[item.get(column, "") for column in columns] for item in self.change_alert_rows]
    return export_table_data(file_path, columns, rows, sheet_name="变更提醒")

@register("export_run_records")
def export_run_records(self):
    if not self.run_records:
        self.run_records = self.database.recent_runs(1000)
    if not self.run_records:
        QMessageBox.information(self, "提示", "没有可导出的任务档案。")
        return
    columns = ["ID", "开始时间", "结束时间", "状态", "网址", "模板", "AI 厂商", "模型", "结果数", "配置快照", "风险检查"]
    rows = []
    for run in self.run_records:
        rows.append(
            [
                run.get("id", ""),
                run.get("started_at", ""),
                run.get("finished_at", ""),
                run.get("status", ""),
                "\n".join(run.get("urls", []) or []),
                run.get("template_name", ""),
                run.get("ai_provider", ""),
                run.get("model", ""),
                run.get("result_count", 0),
                json.dumps(run.get("config", {}), ensure_ascii=False),
                json.dumps(run.get("risks", []), ensure_ascii=False),
            ]
        )
    file_path, selected = QFileDialog.getSaveFileName(
        self,
        "导出任务运行档案",
        export_default_path("任务运行档案.xlsx"),
        "Excel 文件 (*.xlsx);;CSV 文件 (*.csv);;JSON 文件 (*.json)",
    )
    if not file_path:
        return
    file_path = selected_export_path(file_path, selected)
    try:
        export_table_data(file_path, columns, rows, sheet_name="任务运行档案")
    except Exception as exc:
        QMessageBox.warning(self, "导出失败", str(exc))
        return
    QMessageBox.information(self, "导出成功", f"已导出：\n{file_path}")

@register("export_selected_run_results")
def export_selected_run_results(self):
    run = self.selected_run_record()
    if not run:
        QMessageBox.information(self, "提示", "请先在任务档案表里选择一条记录。")
        return
    records = self.database.records_for_run(run.get("id"), 10000)
    if not records:
        QMessageBox.information(self, "提示", "当前任务还没有可导出的采集结果。")
        return
    default_name = f"任务{run.get('id')}_采集结果.xlsx"
    file_path, selected = QFileDialog.getSaveFileName(
        self,
        "导出当前任务结果",
        export_default_path(default_name),
        "Excel 文件 (*.xlsx);;CSV 文件 (*.csv)",
    )
    if not file_path:
        return
    file_path = selected_export_path(file_path, selected)
    try:
        export_records(file_path, records)
    except Exception as exc:
        QMessageBox.warning(self, "导出失败", str(exc))
        return
    QMessageBox.information(self, "导出成功", f"已导出：\n{file_path}")

@register("export_records_dialog")
def export_records_dialog(self, records, title):
    if not records:
        QMessageBox.information(self, "提示", "没有可导出的数据。")
        return
    file_path, selected = QFileDialog.getSaveFileName(
        self,
        title,
        export_default_path("通用采集结果.xlsx"),
        "Excel 文件 (*.xlsx);;CSV 文件 (*.csv)",
    )
    if not file_path:
        return
    file_path = selected_export_path(file_path, selected)
    try:
        export_records(file_path, records)
    except Exception as exc:
        QMessageBox.warning(self, "导出失败", str(exc))
        return
    QMessageBox.information(self, "导出成功", f"已导出：\n{file_path}")
