"""Simple result summary, preview, and export helpers."""

from ui_registry import register

from PyQt6.QtCore import Qt
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QMessageBox, QTableWidgetItem

import os
import time
from universal_core import compact_text, export_records, export_table_data
from core_export import export_records, export_table_data
from ui_export_utils import export_default_dir

@register("simple_result_summary_text")
def simple_result_summary_text(self):
    if not getattr(self, "records", []):
        return "结果：暂无"
    counts = {"新增": 0, "变化": 0, "重复": 0, "错误": 0}
    scores = []
    for record in self.records:
        self.ensure_record_completeness(record)
        status = self.record_status_text(record)
        counts[status] = counts.get(status, 0) + 1
        scores.append(int(record.get("completeness_score") or 0))
    parts = [f"{name} {count}" for name, count in counts.items() if count]
    average = int(sum(scores) / len(scores)) if scores else 0
    return f"结果：共 {len(self.records)} 条，平均完整度 {average}%，" + "，".join(parts)

@register("refresh_simple_crawl_diagnosis")
def refresh_simple_crawl_diagnosis(self):
    if hasattr(self, "simple_diagnosis_label"):
        self.simple_diagnosis_label.setText(self.simple_crawl_diagnosis_text())
    if hasattr(self, "simple_repair_plan_label"):
        self.simple_repair_plan_label.setText(self.simple_repair_plan_text())

@register("refresh_simple_result_summary")
def refresh_simple_result_summary(self):
    if hasattr(self, "simple_result_summary_label"):
        self.simple_result_summary_label.setText(self.simple_result_summary_text())
    self.refresh_simple_crawl_diagnosis()

@register("selected_simple_record")
def selected_simple_record(self):
    if not hasattr(self, "simple_result_table"):
        return None
    return self.selected_record_from_table(self.simple_result_table)

@register("simple_result_counts_text")
def simple_result_counts_text(self, record):
    if not record:
        return "图片 0｜链接 0｜表格 0"
    self.ensure_record_completeness(record)
    return (
        f"图片 {len(record.get('images', []) or [])}"
        f"｜链接 {len(record.get('links', []) or [])}"
        f"｜表格 {len(record.get('tables', []) or [])}"
        f"｜完整度 {record.get('completeness_label') or '0% 偏少'}"
    )

@register("update_simple_result_preview")
def update_simple_result_preview(self):
    if not hasattr(self, "simple_preview_title_label"):
        return
    record = self.selected_simple_record()
    if not record:
        self.simple_preview_title_label.setText("未选择结果")
        self.simple_preview_url_label.setText("")
        self.simple_preview_counts_label.setText("图片 0｜链接 0｜表格 0")
        self.simple_preview_body_output.clear()
        return
    self.simple_preview_title_label.setText(record.get("title", "") or "(无标题)")
    self.simple_preview_url_label.setText(record.get("url", ""))
    self.simple_preview_counts_label.setText(self.simple_result_counts_text(record))
    body_text = record.get("body", "")
    if not body_text and record.get("error"):
        body_text = record.get("error", "")
    self.simple_preview_body_output.setPlainText(compact_text(body_text, 1200))

@register("current_save_mode")
def current_save_mode(self):
    if hasattr(self, "simple_save_mode_combo"):
        return self.simple_save_mode_combo.currentData() or "runtime"
    return "runtime"

@register("current_export_base_dir")
def current_export_base_dir(self):
    mode = self.current_save_mode()
    os.environ["UNIVERSAL_COLLECTOR_SAVE_MODE"] = mode
    os.environ["UNIVERSAL_COLLECTOR_PROJECT_ROOT"] = os.getcwd()
    return export_default_dir()

@register("refresh_save_location_hint")
def refresh_save_location_hint(self):
    target_dir = os.path.join(self.current_export_base_dir(), "采集结果导出")
    if hasattr(self, "simple_save_path_label"):
        self.simple_save_path_label.setText(f"保存位置：{target_dir}")
    return target_dir

@register("simple_export_dir")
def simple_export_dir(self):
    export_dir = os.path.join(self.current_export_base_dir(), "采集结果导出")
    os.makedirs(export_dir, exist_ok=True)
    return export_dir

@register("simple_export_filename")
def simple_export_filename(self, prefix):
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return os.path.join(self.simple_export_dir(), f"{prefix}_{stamp}.xlsx")

@register("recent_simple_export_files")
def recent_simple_export_files(self, limit=5):
    export_dir = self.simple_export_dir()
    files = []
    for name in os.listdir(export_dir):
        path = os.path.join(export_dir, name)
        if not os.path.isfile(path) or not name.lower().endswith(".xlsx"):
            continue
        files.append(
            {
                "name": name,
                "path": path,
                "mtime": os.path.getmtime(path),
                "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(path))),
            }
        )
    files.sort(key=lambda item: item.get("mtime", 0), reverse=True)
    return files[: max(1, int(limit or 5))]

@register("refresh_simple_recent_area")
def refresh_simple_recent_area(self):
    if hasattr(self, "simple_recent_files_table"):
        self.simple_recent_files_table.setRowCount(0)
        for source in self.recent_simple_export_files(limit=5):
            row = self.simple_recent_files_table.rowCount()
            self.simple_recent_files_table.insertRow(row)
            values = [source.get("name", ""), source.get("time", ""), source.get("path", "")]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.simple_recent_files_table.setItem(row, column, item)
    if hasattr(self, "simple_recent_records_table"):
        self.simple_recent_records_table.setRowCount(0)
        current_records = list(getattr(self, "records", []) or [])
        history_records = list(getattr(self, "history_records", []) or self.database.recent_records(5))
        records = (list(reversed(current_records)) + history_records)[:5]
        for record in records:
            row = self.simple_recent_records_table.rowCount()
            self.simple_recent_records_table.insertRow(row)
            values = [
                record.get("title", "") or "(无标题)",
                record.get("url", ""),
                record.get("collected_at", ""),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.simple_recent_records_table.setItem(row, column, item)

@register("selected_simple_recent_file_path")
def selected_simple_recent_file_path(self):
    if not hasattr(self, "simple_recent_files_table"):
        return ""
    selected_rows = self.simple_recent_files_table.selectionModel().selectedRows()
    row = selected_rows[0].row() if selected_rows else 0
    if row < 0 or row >= self.simple_recent_files_table.rowCount():
        return ""
    item = self.simple_recent_files_table.item(row, 2)
    return item.text() if item else ""

@register("simple_open_path")
def simple_open_path(self, path):
    target = os.path.abspath(path or "")
    if os.environ.get("UNIVERSAL_COLLECTOR_SELF_TEST") == "1":
        self.last_simple_open_path = target
        return True
    if not target or not os.path.exists(target):
        QMessageBox.information(self, "提示", "文件不存在，请先保存一次结果。")
        return False
    return QDesktopServices.openUrl(QUrl.fromLocalFile(target))

@register("open_selected_simple_recent_file")
def open_selected_simple_recent_file(self):
    file_path = self.selected_simple_recent_file_path()
    if not file_path:
        QMessageBox.information(self, "提示", "请先选择一个最近保存的 Excel。")
        return False
    return self.simple_open_path(file_path)

@register("open_simple_recent_export_folder")
def open_simple_recent_export_folder(self):
    return self.simple_open_path(self.simple_export_dir())

@register("simple_information")
def simple_information(self, title, message):
    if os.environ.get("UNIVERSAL_COLLECTOR_SELF_TEST") == "1":
        self.last_simple_message = (title, message)
        return
    QMessageBox.information(self, title, message)

@register("simple_auto_save_results")
def simple_auto_save_results(self):
    if getattr(self, "records", []):
        columns, rows = self.simple_field_table_data()
        file_path = self.simple_export_filename("按要求整理结果" if columns and rows else "网页采集结果")
        try:
            if columns and rows:
                export_table_data(file_path, columns, rows, sheet_name="按要求整理结果")
            else:
                export_records(file_path, self.records)
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return False
        self.simple_progress_label.setText(f"已自动保存：{file_path}")
        self.simple_status_label.setText("结果已保存为 Excel")
        self.set_simple_flow_step("导出")
        self.last_simple_export_path = file_path
        self.refresh_simple_recent_area()
        self.simple_information("保存成功", f"已保存：\n{file_path}")
        return True
    columns, rows = self.ai_table_data() if hasattr(self, "ai_table") else ([], [])
    if columns and rows:
        file_path = self.simple_export_filename("文件转表格结果")
        try:
            export_table_data(file_path, columns, rows, sheet_name="文件转表格结果")
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return False
        self.simple_progress_label.setText(f"已自动保存：{file_path}")
        self.simple_status_label.setText("表格已保存为 Excel")
        self.set_simple_flow_step("导出")
        self.last_simple_export_path = file_path
        self.refresh_simple_recent_area()
        self.simple_information("保存成功", f"已保存：\n{file_path}")
        return True
    self.simple_information("提示", "还没有可保存的数据。请先开始采集。")
    return False
