"""File-selection and export helper actions for the universal UI."""

from ui_registry import register

from PyQt6.QtGui import QClipboard
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

import os
from universal_core import download_images_from_records, export_table_data, table_data_to_tsv
from core_export import export_table_data, table_data_to_tsv
from ui_export_utils import export_default_dir, export_default_path, selected_export_path

@register("ai_extract_file")
def ai_extract_file(self):
    file_path, _ = QFileDialog.getOpenFileName(
        self,
        "选择 PDF / 图片 / 文本",
        export_default_dir(),
        "可提取文件 (*.pdf *.png *.jpg *.jpeg *.webp *.bmp *.txt *.csv);;所有文件 (*.*)",
    )
    if not file_path:
        return
    instruction = self.ai_prompt_input.toPlainText().strip()
    self.run_ai_worker(
        "extract_file",
        {
            "file_path": file_path,
            "instruction": instruction,
            "firecrawl_config": self.current_firecrawl_config(include_secret=True),
        },
    )

@register("download_current_images")
def download_current_images(self):
    records = self.records or self.database.recent_records(200)
    if not records:
        QMessageBox.information(self, "提示", "没有可下载图片的采集结果。")
        return
    target_dir = QFileDialog.getExistingDirectory(self, "选择图片保存目录", export_default_dir())
    if not target_dir:
        return
    if os.environ.get("UNIVERSAL_COLLECTOR_SELF_TEST") == "1":
        saved = download_images_from_records(records, target_dir, logger=self.append_ai_output)
        self.image_download_context = "ai"
        self.on_image_download_result(saved, target_dir)
        self.image_download_context = ""
        return
    self.start_image_download(records, target_dir, context="ai")

@register("export_ai_table")
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

@register("copy_ai_table_to_clipboard")
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

@register("import_urls")
def import_urls(self):
    file_path, _ = QFileDialog.getOpenFileName(
        self,
        "导入网址",
        export_default_dir(),
        "文本文件 (*.txt *.csv);;所有文件 (*.*)",
    )
    if not file_path:
        return
    with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
        urls = []
        for line in f:
            for part in line.replace(",", "\n").splitlines():
                if part.strip().startswith(("http://", "https://")):
                    urls.append(part.strip())
    self.url_input.setPlainText("\n".join(urls))
    self.append_log(f"已导入 {len(urls)} 个网址。")
