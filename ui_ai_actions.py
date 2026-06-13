"""AI task execution and current-record action helpers."""

from ui_registry import register

import os

from PyQt6.QtWidgets import QFileDialog, QMessageBox

from universal_core import (
    download_images_from_records,
    extract_emails_and_phones,
    page_snapshot_from_html,
)
from ui_export_utils import export_default_dir


@register("ai_generate_task")
def ai_generate_task(self):
    prompt = self.ai_prompt_input.toPlainText().strip()
    if not prompt:
        QMessageBox.information(self, "提示", "请先描述要抓取什么。")
        return
    url = self.first_target_url()
    snapshot = {}
    if url:
        try:
            snapshot = page_snapshot_from_html(url, self.fetch_snapshot_html(url))
        except Exception as exc:
            self.append_ai_output(f"网页快照读取失败，仅按文字需求生成：{exc}")
    self.run_ai_worker("parse_task", {"prompt": prompt, "snapshot": snapshot})

@register("ai_run_agent")
def ai_run_agent(self):
    url = self.first_target_url()
    if not url:
        QMessageBox.information(self, "提示", "请先输入网址。")
        return
    plan = self.latest_ai_result if isinstance(self.latest_ai_result, dict) else {}
    actions = plan.get("actions") if isinstance(plan, dict) else []
    if actions:
        self.show_ai_task_plan(plan)
        self.append_ai_output(f"将按预览计划执行 {len(actions)} 个 Agent 动作。")
    if not actions:
        actions = [
            {
                "type": "extract",
                "template_name": self.selected_template_name(),
                "field_rules": [rule.to_dict() for rule in self.collect_field_rules_from_table()],
            }
        ]
    self.run_ai_worker(
        "agent",
        {
            "url": url,
            "actions": actions,
            "keep_login_state": self.keep_login_checkbox.isChecked(),
            "headless": True,
        },
    )

@register("ai_transform_current_records")
def ai_transform_current_records(self):
    if not self.records:
        QMessageBox.information(self, "提示", "请先完成一次网页采集。")
        return
    instruction = self.ai_prompt_input.toPlainText().strip() or "整理成更适合表格分析的字段"
    self.run_ai_worker("transform_records", {"records": self.records, "instruction": instruction})

def ai_extract_file(self):
    if not self.ensure_ai_group_ready(need_search=False):
        return False
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

@register("extract_email_phone_current")
def extract_email_phone_current(self):
    records = self.records or self.database.recent_records(200)
    result = extract_emails_and_phones(records)
    self.show_ai_json(result)
    rows = [
        [
            item.get("content", ""),
            item.get("type", ""),
            item.get("source_title", ""),
            item.get("source_url", ""),
        ]
        for item in result.get("rows", [])
    ]
    self.fill_ai_table(["内容", "类型", "来源标题", "来源网址"], rows)
    self.append_ai_output(f"线索提取完成：邮箱 {len(result.get('emails', []))} 个，电话 {len(result.get('phones', []))} 个。")

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
