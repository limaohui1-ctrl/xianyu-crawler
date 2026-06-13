"""AI worker, image download, and thread management."""

from ui_registry import register

from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import QInputDialog, QMessageBox

import os
from universal_core import UniversalCollector, normalize_url
from core_urls import normalize_url
from ui_workers import AIWorker, ImageDownloadWorker

@register("run_ai_worker")
def run_ai_worker(self, action, payload=None):
    if self.ai_worker:
        QMessageBox.information(self, "提示", "已有 AI 任务正在运行，请稍等。")
        return
    self.save_ai_settings_from_ui()
    self.ai_thread = QThread(self)
    self.ai_worker = AIWorker(action, self.ai_settings, payload or {})
    self.ai_worker.moveToThread(self.ai_thread)
    self.ai_thread.started.connect(self.ai_worker.run)
    self.ai_worker.log_signal.connect(self.append_ai_output)
    self.ai_worker.result_signal.connect(self.on_ai_result)
    self.ai_worker.finished_signal.connect(self.ai_thread.quit)
    self.ai_worker.finished_signal.connect(self.ai_worker.deleteLater)
    self.ai_thread.finished.connect(self.ai_thread.deleteLater)
    self.ai_thread.finished.connect(self.on_ai_finished)
    self.append_ai_output(f"开始 AI 任务：{action}")
    self.ai_thread.start()

@register("start_image_download")
def start_image_download(self, records, target_dir, context="ai"):
    if self.image_download_thread:
        if context == "simple" and hasattr(self, "simple_status_label"):
            self.simple_status_label.setText("图片正在后台下载，请稍等")
        else:
            QMessageBox.information(self, "提示", "图片正在后台下载，请稍等。")
        return False
    self.image_download_context = context
    self.latest_image_download_rows = []
    if context == "simple":
        if hasattr(self, "simple_status_label"):
            self.simple_status_label.setText("图片正在后台下载")
        if hasattr(self, "simple_progress_label"):
            self.simple_progress_label.setText(f"后台：图片会保存到 {target_dir}")
        if hasattr(self, "simple_image_button"):
            self.simple_image_button.setEnabled(False)
            self.simple_image_button.setText("下载中")
    self.image_download_thread = QThread(self)
    self.image_download_worker = ImageDownloadWorker(records, target_dir)
    self.image_download_worker.moveToThread(self.image_download_thread)
    self.image_download_thread.started.connect(self.image_download_worker.run)
    self.image_download_worker.log_signal.connect(self.append_ai_output)
    self.image_download_worker.result_signal.connect(self.on_image_download_result)
    self.image_download_worker.finished_signal.connect(self.image_download_thread.quit)
    self.image_download_worker.finished_signal.connect(self.image_download_worker.deleteLater)
    self.image_download_thread.finished.connect(self.image_download_thread.deleteLater)
    self.image_download_thread.finished.connect(self.on_image_download_finished)
    self.append_ai_output(f"开始后台下载图片：{target_dir}")
    self.image_download_thread.start()
    return True

@register("on_image_download_result")
def on_image_download_result(self, saved, target_dir):
    saved = list(saved or [])
    self.latest_image_download_rows = saved
    rows = [
        [
            item.get("status", ""),
            item.get("file_path", ""),
            item.get("image_url", ""),
            item.get("source_title", ""),
            item.get("source_url", ""),
            item.get("size_bytes", ""),
            item.get("error", ""),
        ]
        for item in saved
    ]
    self.fill_ai_table(["状态", "保存路径", "图片网址", "来源标题", "来源网址", "大小字节", "错误"], rows)
    saved_count = sum(1 for item in saved if item.get("status") == "已保存")
    failed_count = sum(1 for item in saved if item.get("status") != "已保存")
    self.append_ai_output(f"图片下载完成：成功 {saved_count} 张，失败 {failed_count} 张。")
    context = getattr(self, "image_download_context", "")
    if context == "simple":
        if hasattr(self, "simple_status_label"):
            self.simple_status_label.setText(f"图片下载完成：成功 {saved_count} 张，失败 {failed_count} 张")
        if hasattr(self, "simple_progress_label"):
            self.simple_progress_label.setText(f"图片保存位置：{target_dir}")
        self.simple_information("图片下载完成", f"成功 {saved_count} 张，失败 {failed_count} 张。\n{target_dir}")
    else:
        QMessageBox.information(self, "图片下载完成", f"成功 {saved_count} 张，失败 {failed_count} 张。结果已放入 AI 表格，可导出或复制。")
        self.show_ai_json({"saved": saved})

@register("on_image_download_finished")
def on_image_download_finished(self):
    if hasattr(self, "simple_image_button"):
        self.simple_image_button.setEnabled(True)
        self.simple_image_button.setText("下载图片")
    self.image_download_thread = None
    self.image_download_worker = None
    self.image_download_context = ""
    self.append_ai_output("图片下载任务结束。")

@register("on_ai_finished")
def on_ai_finished(self):
    self.ai_worker = None
    self.ai_thread = None
    self.refresh_ai_call_logs()
    self.append_ai_output("AI 任务结束。")

@register("first_target_url")
def first_target_url(self):
    url = normalize_url(self.ai_url_input.text())
    if url:
        return url
    urls = self.urls_from_input()
    return urls[0] if urls else ""

@register("fetch_snapshot_html")
def fetch_snapshot_html(self, url):
    return UniversalCollector(logger=self.append_ai_output).fetch_with_playwright(
        url,
        scroll_times=self.scroll_times_input.value(),
        keep_login_state=self.keep_login_checkbox.isChecked(),
    )

@register("simple_int_dialog")
def simple_int_dialog(self, title, label, value, minimum, maximum):
    from PyQt6.QtWidgets import QInputDialog
    value, ok = QInputDialog.getInt(self, title, label, value, minimum, maximum)
    return value if ok else None