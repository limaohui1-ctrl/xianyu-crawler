"""Result table context-menu actions: copy row, open URL, export selected rows."""

from ui_registry import register

import csv
import os
import tempfile

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication, QTableWidget


@register("on_result_table_context_menu")
def on_result_table_context_menu(self, pos):
    table = self.sender()
    if not isinstance(table, QTableWidget):
        return
    row = table.rowAt(pos.y())
    if row < 0 or row >= table.rowCount():
        return
    if not table.selectedIndexes():
        table.selectRow(row)
    menu = QTableWidget.createStandardContextMenu(self)
    menu.addSeparator()
    copy_row_action = menu.addAction("复制整行")
    copy_row_action.triggered.connect(lambda: _copy_selected_table_row(self, table, row))
    open_url_action = menu.addAction("打开网址")
    open_url_action.triggered.connect(lambda: _open_selected_table_url(self, table, row))
    export_selected_action = menu.addAction("导出选中行")
    export_selected_action.triggered.connect(lambda: _export_selected_table_rows(self, table))
    menu.exec(table.viewport().mapToGlobal(pos))


def _copy_selected_table_row(self, table, row):
    values = []
    for col in range(table.columnCount()):
        item = table.item(row, col)
        values.append(item.text() if item else "")
    QApplication.clipboard().setText("\t".join(values))
    self.append_log(f"[已复制第 {row + 1} 行到剪贴板]")


def _open_selected_table_url(self, table, row):
    url = ""
    for col in range(table.columnCount()):
        header = table.horizontalHeaderItem(col)
        if header and header.text() in ("网址", "链接", "url", "URL"):
            item = table.item(row, col)
            url = item.text() if item else ""
            break
    if not url and table.columnCount() >= 2:
        item = table.item(row, 1)
        url = item.text() if item else ""
    if url and url.startswith(("http://", "https://")):
        QDesktopServices.openUrl(QUrl(url))


def _export_selected_table_rows(self, table):
    selected = set()
    for index in table.selectedIndexes():
        selected.add(index.row())
    if not selected:
        return
    columns = []
    for col in range(table.columnCount()):
        header = table.horizontalHeaderItem(col)
        columns.append(header.text() if header else f"列{col + 1}")
    rows = []
    for row in sorted(selected):
        values = []
        for col in range(table.columnCount()):
            item = table.item(row, col)
            values.append(item.text() if item else "")
        rows.append(values)
    fd, path = tempfile.mkstemp(suffix=".csv", prefix="selected_rows_")
    with os.fdopen(fd, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    self.append_log(f"[已导出 {len(rows)} 行到临时 CSV]")
