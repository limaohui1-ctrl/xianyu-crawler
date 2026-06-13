"""Natural-language web crawl result application helpers."""

from ui_registry import register

from PyQt6.QtWidgets import QMessageBox

import json
import os
from universal_core import FieldRule, export_table_data, url_domain
from core_export import export_table_data
from core_urls import url_domain
from ui_export_utils import export_default_dir

@register("nl_result_to_task_plan")
def nl_result_to_task_plan(self, result):
    result = result if isinstance(result, dict) else {}
    items = result.get("items", []) or []
    columns = []
    if items and isinstance(items[0], dict):
        for item in items:
            if isinstance(item, dict):
                for key in item.keys():
                    if key not in columns:
                        columns.append(key)
    field_rules = []
    for key in columns[:8]:
        field_rules.append({"name": str(key), "selector": f"[data-field='{key}']", "attr": "text", "multiple": False, "reason": "由自然语言全网爬取结果自动生成字段草案"})
    return {
        "template": {
            "name": "自然语言全网爬取模板",
            "domain": url_domain((result.get("urls") or [""])[0] if result.get("urls") else ""),
            "template_type": "auto",
            "next_page_selector": "",
            "field_rules": field_rules,
            "notes": "由自然语言全网爬取结果生成。",
        },
        "options": {
            "use_browser": True,
            "scroll_times": 2,
            "page_limit": 3,
            "subpage_limit": 0,
        },
        "actions": [
            {"type": "extract", "template_name": "自然语言全网爬取模板", "field_rules": field_rules}
        ],
        "page_kind": "全网汇总",
    }

@register("apply_nl_result_as_task_plan")
def apply_nl_result_as_task_plan(self):
    result = self.latest_ai_result if isinstance(self.latest_ai_result, dict) else {}
    items = result.get("items", []) if isinstance(result, dict) else []
    if not items:
        QMessageBox.information(self, "提示", "请先运行自然语言全网爬取或演练模式。")
        return False
    plan = self.nl_result_to_task_plan(result)
    self.latest_ai_result = plan
    self.apply_ai_task(plan)
    self.show_main_tab("AI 抓取工作台")
    self.append_ai_output("已把自然语言全网爬取结果转换为采集任务草案。")
    return True

@register("apply_nl_result_to_batch_collect")
def apply_nl_result_to_batch_collect(self):
    if not self.apply_nl_result_as_task_plan():
        return False
    self.collect_progress_label.setText("自然语言结果已转为批量采集任务草案，可直接开始采集。")
    self.append_ai_output("自然语言全网爬取结果已一键应用到批量采集。")
    return True

@register("apply_nl_result_as_template_draft")
def apply_nl_result_as_template_draft(self):
    result = self.latest_ai_result if isinstance(result := self.latest_ai_result, dict) else {}
    items = result.get("items", []) if isinstance(result, dict) else []
    if not items:
        QMessageBox.information(self, "提示", "请先运行自然语言全网爬取或演练模式。")
        return False
    plan = self.nl_result_to_task_plan(result)
    template_data = plan.get("template", {})
    self.template_name_input.setText(template_data.get("name", "自然语言全网爬取模板"))
    self.template_domain_input.setText(template_data.get("domain", ""))
    idx = self.template_type_combo.findData(template_data.get("template_type", "auto"))
    if idx >= 0:
        self.template_type_combo.setCurrentIndex(idx)
    self.next_page_selector_input.setText(template_data.get("next_page_selector", ""))
    self.template_notes_input.setPlainText(template_data.get("notes", ""))
    self.field_table.setRowCount(0)
    for field in template_data.get("field_rules", []):
        self.add_field_row(FieldRule.from_dict(field))
    self.show_main_tab("模板库")
    self.append_ai_output("已把自然语言全网爬取结果转换为模板草案。")
    return True

@register("save_natural_language_demo_report")
def save_natural_language_demo_report(self):
    result = self.latest_ai_result if isinstance(self.latest_ai_result, dict) else {}
    items = result.get("items", []) if isinstance(result, dict) else []
    if not items:
        QMessageBox.information(self, "提示", "还没有可保存的演练结果，请先运行一次演练模式。")
        return False
    columns = []
    for item in items:
        if isinstance(item, dict):
            for key in item.keys():
                if key not in columns:
                    columns.append(key)
    rows = []
    for item in items:
        if isinstance(item, dict):
            rows.append([json.dumps(item.get(col, ""), ensure_ascii=False) if isinstance(item.get(col, ""), (dict, list)) else item.get(col, "") for col in columns])
    file_path = self.simple_export_filename("自然语言全网爬取演练报告") if hasattr(self, "simple_export_filename") else os.path.join(export_default_dir(), "自然语言全网爬取演练报告.xlsx")
    export_table_data(file_path, columns, rows, sheet_name="自然语言演练结果")
    self.append_ai_output(f"已保存自然语言全网爬取演练报告：{file_path}")
    QMessageBox.information(self, "保存成功", f"已保存：\n{file_path}")
    return True

@register("run_natural_language_web_crawl_demo")
def run_natural_language_web_crawl_demo(self):
    prompt = self.ai_nl_prompt_input.toPlainText().strip() if hasattr(self, "ai_nl_prompt_input") else ""
    if not prompt:
        QMessageBox.information(self, "提示", "请先输入全网采集需求。")
        return
    if hasattr(self, "hero_status_label"):
        self.hero_status_label.setText("状态：自然语言全网爬取演练中")
    self.run_ai_worker(
        "natural_language_web_crawl",
        {
            "prompt": prompt,
            "search_provider": "serper",
            "max_search_results": 3,
            "timeout_seconds": 5.0,
            "page_timeout_seconds": 5.0,
            "demo_mode": True,
        },
    )

@register("run_natural_language_web_crawl")
def run_natural_language_web_crawl(self):
    if not self.ensure_ai_group_ready(need_search=True):
        return False
    prompt = self.ai_nl_prompt_input.toPlainText().strip() if hasattr(self, "ai_nl_prompt_input") else ""
    if not prompt:
        QMessageBox.information(self, "提示", "请先输入全网采集需求。")
        return
    settings = self.collect_ai_settings_from_ui()
    if not str(settings.get("search_api_key") or "").strip():
        message = self.search_health_summary_text(settings)
        if hasattr(self, "ai_search_health_label"):
            self.ai_search_health_label.setText(message)
        QMessageBox.information(self, "搜索配置未完成", message + "。请先在 AI 配置区填写搜索 API Key。")
        return
    provider = self.ai_nl_search_provider_combo.currentData() if hasattr(self, "ai_nl_search_provider_combo") else "serper"
    max_results = self.ai_nl_max_results_input.value() if hasattr(self, "ai_nl_max_results_input") else 5
    if hasattr(self, "hero_status_label"):
        self.hero_status_label.setText("状态：自然语言全网爬取执行中")
    self.run_ai_worker(
        "natural_language_web_crawl",
        {
            "prompt": prompt,
            "search_provider": provider,
            "max_search_results": max_results,
            "timeout_seconds": 20.0,
            "page_timeout_seconds": 12.0,
        },
    )
