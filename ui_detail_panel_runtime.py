"""Image/link/table preview and open helpers."""

from ui_registry import register

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QPixmap
from PyQt6.QtWidgets import QLabel, QTableWidgetItem, QMessageBox

from universal_core import compact_text, normalize_url


@register("clear_image_preview")
def clear_image_preview(self):
    while self.image_layout.count():
        item = self.image_layout.takeAt(0)
        widget = item.widget()
        if widget:
            widget.deleteLater()
    self.image_layout.addStretch(1)

@register("update_image_preview")
def update_image_preview(self, images):
    self.clear_image_preview()
    for image in images[:8]:
        image_url = image.get("url", "") if isinstance(image, dict) else str(image)
        label = QLabel()
        label.setFixedSize(112, 92)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setToolTip(image_url)
        pixmap = self.load_image_pixmap(image_url)
        if pixmap and not pixmap.isNull():
            label.setPixmap(
                pixmap.scaled(
                    108,
                    88,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            label.setText("图片")
        self.image_layout.insertWidget(self.image_layout.count() - 1, label)

@register("load_image_pixmap")
def load_image_pixmap(self, image_url):
    if not image_url:
        return None
    try:
        request = Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=5) as response:
            data = response.read(1024 * 1024)
    except Exception:
        return None
    pixmap = QPixmap()
    if pixmap.loadFromData(data):
        return pixmap
    return None

@register("update_link_preview")
def update_link_preview(self, links):
    self.fill_link_table(self.detail_link_table, links)

@register("fill_link_table")
def fill_link_table(self, table, links):
    table.setRowCount(0)
    for link in links[:50]:
        if isinstance(link, dict):
            text = link.get("text", "")
            url = link.get("url", "")
        else:
            text = ""
            url = str(link)
        row = table.rowCount()
        table.insertRow(row)
        table.setItem(row, 0, QTableWidgetItem(text))
        table.setItem(row, 1, QTableWidgetItem(url))

@register("update_table_preview")
def update_table_preview(self, tables):
    self.fill_table_widget(self.detail_table_view, tables)

@register("fill_table_widget")
def fill_table_widget(self, table_widget, tables):
    table_widget.setRowCount(0)
    table_widget.setColumnCount(0)
    if not tables:
        return
    first_table = tables[0]
    if not isinstance(first_table, list) or not first_table:
        return
    column_count = max((len(row) for row in first_table if isinstance(row, list)), default=0)
    table_widget.setColumnCount(column_count)
    for source_row in first_table[:100]:
        if not isinstance(source_row, list):
            continue
        row = table_widget.rowCount()
        table_widget.insertRow(row)
        for column, value in enumerate(source_row[:column_count]):
            table_widget.setItem(row, column, QTableWidgetItem(str(value)))

@register("open_selected_url")
def open_selected_url(self):
    record = self.selected_record_from_table(self.result_table)
    if not record:
        QMessageBox.information(self, "提示", "请先选择一条结果。")
        return
    QDesktopServices.openUrl(QUrl(record.get("url", "")))

@register("clear_current_results")
def clear_current_results(self):
    self.records.clear()
    self.result_table.setRowCount(0)
    if hasattr(self, "simple_result_table"):
        self.simple_result_table.setRowCount(0)
    self.simple_merge_subpage_results = False
    self.simple_subpage_parent_map = {}
    if hasattr(self, "simple_preview_title_label"):
        self.update_simple_result_preview()
    if hasattr(self, "simple_field_table"):
        self.refresh_simple_field_table()
    if hasattr(self, "simple_status_label"):
        self.simple_status_label.setText("准备就绪")
    if hasattr(self, "simple_progress_label"):
        self.simple_progress_label.setText("流程：输入网址 -> 开始采集 -> 导出结果")
    self.low_quality_retry_baseline = {}
    self.low_quality_retry_active = False
    self.low_quality_retry_report_rows = []
    self.latest_crawl_discovery_messages = []
    self.refresh_low_quality_retry_report_summary()
    if hasattr(self, "simple_discovery_label"):
        self.simple_discovery_label.setText("发现记录：等待采集")
    self.set_simple_flow_step("输入")
    self.refresh_simple_result_summary()
    self.refresh_result_status_summary()
    self.fill_result_quality_table([])
    self.refresh_new_user_flow_status("prepared")
