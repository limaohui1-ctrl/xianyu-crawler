"""AI table fill, data, and clipboard helpers."""

from ui_registry import register

from PyQt6.QtGui import QClipboard
from PyQt6.QtWidgets import QApplication, QFileDialog, QHeaderView, QMessageBox, QTableWidgetItem

from universal_core import export_table_data, table_data_to_tsv
from core_export import export_table_data, table_data_to_tsv
from ui_export_utils import export_default_path, selected_export_path

@register("apply_ai_table_result")
def apply_ai_table_result(self, result):
    if not isinstance(result, dict):
        return
    columns = result.get("columns") or []
    rows = result.get("rows") or []
    self.fill_ai_table(columns, rows)

@register("fill_ai_table")
def fill_ai_table(self, columns, rows):
    self.ai_table.setRowCount(0)
    self.ai_table.setColumnCount(len(columns))
    self.ai_table.setHorizontalHeaderLabels([str(item) for item in columns])
    for source_row in rows:
        row = self.ai_table.rowCount()
        self.ai_table.insertRow(row)
        values = source_row if isinstance(source_row, list) else [source_row]
        for column, value in enumerate(values[: len(columns)]):
            self.ai_table.setItem(row, column, QTableWidgetItem(str(value)))
    for column in range(len(columns)):
        self.ai_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)

@register("ai_table_data")
def ai_table_data(self):
    columns = []
    for column in range(self.ai_table.columnCount()):
        header = self.ai_table.horizontalHeaderItem(column)
        columns.append(header.text() if header else f"字段{column + 1}")
    rows = []
    for row in range(self.ai_table.rowCount()):
        values = []
        for column in range(self.ai_table.columnCount()):
            item = self.ai_table.item(row, column)
            values.append(item.text() if item else "")
        rows.append(values)
    return columns, rows

def export_ai_table(self):
    columns, rows = self.ai_table_data()
    if not columns or not rows:
        QMessageBox.information(self, "提示", "AI 表格里没有可导出的数据。")
        return
    file_path, selected = QFileDialog.getSaveFileName(
        self,
        "导出 AI 表格",
        export_default_path("AI表格结果.xlsx"),
        "Excel 文件 (*.xlsx);;CSV 文件 (*.csv);;JSON 文件 (*.json)",
    )
    if not file_path:
        return
    file_path = selected_export_path(file_path, selected)
    try:
        export_table_data(file_path, columns, rows, sheet_name="AI表格结果")
    except Exception as exc:
        QMessageBox.warning(self, "导出失败", str(exc))
        return
    self.append_ai_output(f"AI 表格已导出：{file_path}")
    QMessageBox.information(self, "导出成功", f"已导出：\n{file_path}")

def copy_ai_table_to_clipboard(self):
    columns, rows = self.ai_table_data()
    if not columns or not rows:
        QMessageBox.information(self, "提示", "AI 表格里没有可复制的数据。")
        return
    clipboard = QApplication.clipboard()
    clipboard.clear()
    copied_text = table_data_to_tsv(columns, rows)
    clipboard.setText(copied_text, mode=QClipboard.Mode.Clipboard)
    self.last_clipboard_text = copied_text
    QApplication.processEvents()
    self.append_ai_output(f"已复制 AI 表格：{len(rows)} 行，{len(columns)} 列。")
