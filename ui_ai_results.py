"""AI worker result callback and field/task-plan application helpers."""

from ui_registry import register

import json
import time

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QClipboard
from PyQt6.QtWidgets import QApplication, QComboBox, QMessageBox, QTableWidgetItem

from universal_core import (
    FieldRule,
    SiteTemplate,
    UniversalExtractor,
    mask_api_key,
    normalize_api_key_entries,
    normalize_url,
    save_ai_settings,
    url_domain,
)
from core_urls import (
    normalize_url,
    url_domain,
)

from ui_export_utils import export_default_path, selected_export_path


@register("on_ai_result")
def on_ai_result(self, action, result):
    if isinstance(result, dict) and result.get("error"):
        if action == "simple_suggest_fields":
            self.simple_ai_suggest_pending = False
            self.simple_ai_field_rules = []
            self.refresh_simple_field_table()
            self.append_ai_output(f"普通首页 AI 建议列失败，已改用本地规则：{result['error']}")
            if hasattr(self, "simple_status_label") and not self.worker:
                self.simple_status_label.setText("AI 建议列暂不可用，已用本地规则整理")
            return
        if action == "test_api":
            self.update_current_ai_key_status("失败", result["error"])
        self.append_ai_output(f"AI 任务失败：{result['error']}")
        QMessageBox.warning(self, "AI 任务失败", result["error"])
        return
    self.latest_ai_result = result
    if isinstance(result, dict) and result.get("_auto_switched_key"):
        self.apply_auto_switched_ai_key(result.get("_auto_switched_key", ""))
    self.show_ai_json(result)
    if action == "test_api":
        self.update_current_ai_key_status("可用", "")
        self.append_ai_output("API Key 测试成功，已标记为可用。")
        self.refresh_ai_provider_overview()
    elif action == "diagnose_api":
        self.fill_ai_diagnosis_table(result.get("checks", []) if isinstance(result, dict) else [])
        self.refresh_api_health_summary(result if isinstance(result, dict) else None)
        self.append_ai_output(result.get("summary", "配置诊断完成。") if isinstance(result, dict) else "配置诊断完成。")
        self.refresh_ai_provider_overview()
    elif action == "fetch_models":
        fetched_models = self.unique_models([str(model) for model in result])
        current_model = self.current_ai_model_text()
        self.ai_model_cache = self.unique_models(fetched_models + self.ai_model_cache)
        self.refresh_ai_model_combo(current_model or (self.ai_model_cache[0] if self.ai_model_cache else ""))
        current_settings = self.collect_ai_settings_from_ui()
        current_settings["models_updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        current_settings["models_refresh_error"] = ""
        self.ai_settings = save_ai_settings(current_settings)
        self.append_ai_output(f"已拉取并缓存 {len(fetched_models)} 个模型，当前厂商下次打开会保留。")
        self.refresh_ai_provider_overview()
    elif action == "refresh_provider_models":
        result_settings = result.get("settings", {}) if isinstance(result, dict) else {}
        if isinstance(result_settings, dict):
            self.ai_settings = save_ai_settings(result_settings)
            current_provider = self.ai_provider_combo.currentData() or self.ai_settings.get("provider", "openai")
            provider_settings = (self.ai_settings.get("providers") or {}).get(current_provider, {})
            if provider_settings:
                self.ai_model_cache = self.unique_models(
                    (provider_settings.get("model_cache") or []) + (provider_settings.get("models") or [])
                )
                self.refresh_ai_model_combo(provider_settings.get("model", self.current_ai_model_text()))
        rows = result.get("results", []) if isinstance(result, dict) else []
        success_count = sum(1 for item in rows if item.get("status") == "成功")
        skipped_count = sum(1 for item in rows if item.get("status") == "跳过")
        failed_count = sum(1 for item in rows if item.get("status") == "失败")
        self.fill_ai_diagnosis_table(
            [
                {
                    "level": "正常" if item.get("status") == "成功" else "需确认",
                    "item": item.get("provider_name", item.get("provider", "")),
                    "status": f"{item.get('status')}｜{item.get('model_count', 0)} 个",
                    "advice": item.get("message", ""),
                }
                for item in rows
            ]
        )
        self.append_ai_output(f"批量刷新模型完成：成功 {success_count}，跳过 {skipped_count}，失败 {failed_count}。")
        self.refresh_api_health_summary()
        self.refresh_ai_provider_overview()
    elif action == "test_provider_connectivity":
        result_settings = result.get("settings", {}) if isinstance(result, dict) else {}
        if isinstance(result_settings, dict):
            self.ai_settings = save_ai_settings(result_settings)
            current_provider = self.ai_provider_combo.currentData() or self.ai_settings.get("provider", "openai")
            provider_settings = (self.ai_settings.get("providers") or {}).get(current_provider, {})
            if provider_settings:
                self.ai_key_entries = normalize_api_key_entries(
                    provider_settings.get("api_keys"),
                    provider_settings.get("api_key", ""),
                    provider_settings.get("active_api_key_name", ""),
                )
                self.refresh_ai_key_combo(provider_settings.get("active_api_key_name", ""))
        rows = result.get("results", []) if isinstance(result, dict) else []
        success_count = sum(1 for item in rows if item.get("status") == "成功")
        skipped_count = sum(1 for item in rows if item.get("status") == "跳过")
        failed_count = sum(1 for item in rows if item.get("status") == "失败")
        self.fill_ai_diagnosis_table(
            [
                {
                    "level": "正常" if item.get("status") == "成功" else "需确认",
                    "item": item.get("provider_name", item.get("provider", "")),
                    "status": f"{item.get('status')}｜{item.get('model', '')}",
                    "advice": item.get("message", ""),
                }
                for item in rows
            ]
        )
        self.append_ai_output(f"一键测试模型完成：成功 {success_count}，跳过 {skipped_count}，失败 {failed_count}。")
        self.refresh_api_health_summary()
        self.refresh_ai_provider_overview()
    elif action == "suggest_fields":
        self.apply_ai_fields(result)
    elif action == "simple_suggest_fields":
        self.apply_simple_ai_fields(result)
    elif action == "repair_fields":
        self.apply_repaired_fields(result)
    elif action == "parse_task":
        self.apply_ai_task(result)
    elif action == "natural_language_web_crawl":
        items = result.get("items", []) if isinstance(result, dict) else []
        columns = []
        if items and isinstance(items[0], dict):
            for row in items:
                if not isinstance(row, dict):
                    continue
                for key in row.keys():
                    if key not in columns:
                        columns.append(key)
        rows = []
        for item in items:
            if isinstance(item, dict):
                rows.append([
                    json.dumps(item.get(col, ""), ensure_ascii=False) if isinstance(item.get(col, ""), (dict, list)) else item.get(col, "")
                    for col in columns
                ])
            else:
                rows.append([str(item)])
        if columns and rows:
            self.fill_ai_table(columns, rows)
        if hasattr(self, "ai_task_plan_label"):
            mode_text = "演练模式" if result.get("demo_mode") else "真实模式"
            self.ai_task_plan_label.setText(f"自然语言全网爬取（{mode_text}）：命中 {len(items)} 条结构化结果 | 来源 {len(result.get('urls', []))} 个网页")
        self.append_ai_output(f"自然语言全网爬取完成：搜索 {result.get('query', '')}，成功合流 {len(items)} 条结果。")
    elif action == "transform_records":
        self.apply_ai_table_result(result)
    elif action == "extract_file":
        self.apply_ai_table_result(result)
        if hasattr(self, "simple_status_label"):
            if isinstance(result, dict) and result.get("error"):
                self.simple_status_label.setText(f"文件提取失败：{result.get('error')}")
                self.set_simple_flow_step("输入")
            else:
                row_count = len(result.get("rows", []) or []) if isinstance(result, dict) else 0
                self.simple_status_label.setText(f"文件已转成表格，共 {row_count} 行，可以直接自动保存")
                self.simple_progress_label.setText("后台：文件表格已生成")
                self.set_simple_flow_step("导出")
    elif action == "agent":
        records = result.get("records", []) if isinstance(result, dict) else []
        for record in records:
            self.records.append(record)
            self.add_record_to_table(self.result_table, record, "current", len(self.records) - 1)
        self.append_ai_output(f"Agent 已提取 {len(records)} 条记录。")

@register("fill_ai_diagnosis_table")
def fill_ai_diagnosis_table(self, checks):
    self.ai_diagnosis_table.setRowCount(0)
    for check in checks or []:
        if not isinstance(check, dict):
            continue
        row = self.ai_diagnosis_table.rowCount()
        self.ai_diagnosis_table.insertRow(row)
        values = [
            check.get("level", ""),
            check.get("item", ""),
            check.get("status", ""),
            check.get("advice", ""),
        ]
        for column, value in enumerate(values):
            self.ai_diagnosis_table.setItem(row, column, QTableWidgetItem(str(value)))

@register("apply_auto_switched_ai_key")
def apply_auto_switched_ai_key(self, key_name):
    entry = next((item for item in getattr(self, "ai_key_entries", []) if item.get("name") == key_name), None)
    if not entry:
        return
    self.ai_key_name_input.setText(entry.get("name", ""))
    self.ai_key_input.setText(entry.get("key", ""))
    self.refresh_ai_key_combo(entry.get("name", ""))
    self.ai_settings = save_ai_settings(self.collect_ai_settings_from_ui())
    self.append_ai_output(f"已同步当前 Key 为自动重试成功的 Key：{entry.get('name')}（{mask_api_key(entry.get('key'))}）")

@register("show_ai_json")
def show_ai_json(self, result):
    self.ai_output.appendPlainText(json.dumps(result, ensure_ascii=False))

@register("apply_ai_fields")
def apply_ai_fields(self, result):
    fields = result.get("fields") if isinstance(result, dict) else result
    if not isinstance(fields, list):
        self.append_ai_output("AI 没有返回 fields 数组。")
        return
    self.show_ai_suggested_fields(fields)
    self.append_ai_output(f"AI 已建议 {self.ai_suggest_table.rowCount()} 个字段，请勾选后应用到模板。")

@register("apply_repaired_fields")
def apply_repaired_fields(self, result):
    fields = result.get("fields") if isinstance(result, dict) else result
    if not isinstance(fields, list):
        self.append_ai_output("AI 没有返回修复后的 fields 数组。")
        return
    self.show_ai_suggested_fields(fields)
    self.latest_quality_issues = []
    self.fill_quality_table([])
    if self.auto_apply_repair_after_ai:
        self.auto_apply_repair_after_ai = False
        if self.apply_repaired_fields_to_template(auto_preview=True):
            self.append_ai_output(f"AI 已修复并自动应用 {self.ai_suggest_table.rowCount()} 个字段，已重新预采评分。")
            return
    self.append_ai_output(f"AI 已回填 {self.ai_suggest_table.rowCount()} 个修复后字段，可点“应用 AI 修复到模板”后重新预采一页确认。")

@register("apply_repaired_fields_to_template")
def apply_repaired_fields_to_template(self, auto_preview=False):
    rules = self.suggested_field_rules_from_table()
    if not rules:
        QMessageBox.information(self, "提示", "请先让 AI 修复问题列，或在建议列表里保留至少一个字段。")
        return False
    self.field_table.setRowCount(0)
    for rule in rules:
        self.add_field_row(rule)
    self.latest_preview_rules = rules
    preview_done = False
    if auto_preview:
        preview_done = self.preview_with_rules(rules, self.latest_preview_url or self.first_target_url(), self.latest_preview_html)
        if preview_done and self.repair_quality_before_issues:
            repair_fields = [issue.get("field", "") for issue in self.repair_quality_before_issues if issue.get("field")]
            sample_records = self.verify_repaired_fields_on_samples(rules, limit=3)
            self.repair_quality_sample_records = sample_records
            sample_issues = self.analyze_repaired_sample_quality(sample_records, repair_fields) if sample_records else []
            if sample_issues:
                self.update_repair_quality_report(self.repair_quality_before_issues, sample_issues)
                self.append_ai_output(f"已用 {len(sample_records)} 条样本重采验证 AI 修复效果。")
            else:
                self.update_repair_quality_report(self.repair_quality_before_issues, self.latest_quality_issues)
                self.append_ai_output("未找到可重采样本，已用当前预采页验证 AI 修复效果。")
    if not auto_preview:
        self.show_main_tab("模板库")
    message = f"已将 {len(rules)} 个修复字段应用到模板编辑器。"
    if preview_done:
        message += "已自动重新预采并刷新质量评分。"
    else:
        message += "请重新预采确认质量评分。"
    self.append_ai_output(message)
    return True

@register("preview_with_rules")
def preview_with_rules(self, rules, url="", html=""):
    url = normalize_url(url) or self.first_target_url()
    if not url or not html or not rules:
        return False
    try:
        template = SiteTemplate("AI 修复预采模板", field_rules=rules)
        record = UniversalExtractor(template).extract(html, url)
    except Exception as exc:
        self.append_ai_output(f"自动重新预采失败：{exc}")
        return False
    self.latest_preview_url = url
    self.latest_preview_html = html
    self.latest_preview_rules = rules
    self.show_preview_record(record, rules)
    return True

@register("show_ai_suggested_fields")
def show_ai_suggested_fields(self, fields):
    self.ai_suggest_table.setRowCount(0)
    for field in fields:
        if not isinstance(field, dict):
            continue
        row = self.ai_suggest_table.rowCount()
        self.ai_suggest_table.insertRow(row)
        enable_item = QTableWidgetItem()
        enable_item.setCheckState(Qt.CheckState.Checked)
        self.ai_suggest_table.setItem(row, 0, enable_item)
        self.ai_suggest_table.setItem(row, 1, QTableWidgetItem(str(field.get("name", "自定义字段"))))
        self.ai_suggest_table.setItem(row, 2, QTableWidgetItem(str(field.get("selector", ""))))
        attr_combo = QComboBox()
        for attr in ("text", "href", "src", "content", "data-src"):
            attr_combo.addItem(attr)
        attr_value = str(field.get("attr", "text") or "text")
        attr_index = attr_combo.findText(attr_value)
        attr_combo.setCurrentIndex(max(0, attr_index))
        self.ai_suggest_table.setCellWidget(row, 3, attr_combo)
        multi_item = QTableWidgetItem()
        multi_item.setCheckState(Qt.CheckState.Checked if field.get("multiple", False) else Qt.CheckState.Unchecked)
        self.ai_suggest_table.setItem(row, 4, multi_item)
        reason_item = QTableWidgetItem(str(field.get("reason", "")))
        reason_item.setFlags(reason_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.ai_suggest_table.setItem(row, 5, reason_item)

@register("suggested_field_rules_from_table")
def suggested_field_rules_from_table(self):
    rules = []
    for row in range(self.ai_suggest_table.rowCount()):
        enabled = self.ai_suggest_table.item(row, 0)
        if enabled and enabled.checkState() != Qt.CheckState.Checked:
            continue
        name_item = self.ai_suggest_table.item(row, 1)
        selector_item = self.ai_suggest_table.item(row, 2)
        attr_widget = self.ai_suggest_table.cellWidget(row, 3)
        multi_item = self.ai_suggest_table.item(row, 4)
        name = name_item.text().strip() if name_item else ""
        selector = selector_item.text().strip() if selector_item else ""
        if not name or not selector:
            continue
        attr = attr_widget.currentText() if isinstance(attr_widget, QComboBox) else "text"
        multiple = bool(multi_item and multi_item.checkState() == Qt.CheckState.Checked)
        rules.append(FieldRule(name, selector, attr, multiple))
    return rules

@register("apply_checked_ai_fields_to_template")
def apply_checked_ai_fields_to_template(self):
    rules = self.suggested_field_rules_from_table()
    if not rules:
        QMessageBox.information(self, "提示", "请至少保留一个启用的建议列。")
        return
    self.field_table.setRowCount(0)
    for rule in rules:
        self.add_field_row(rule)
    self.show_main_tab("模板库")
    self.append_ai_output(f"已把 {len(rules)} 个已确认建议列应用到模板编辑器。")

@register("select_all_ai_suggested_fields")
def select_all_ai_suggested_fields(self):
    for row in range(self.ai_suggest_table.rowCount()):
        item = self.ai_suggest_table.item(row, 0)
        if item:
            item.setCheckState(Qt.CheckState.Checked)

@register("clear_ai_suggested_fields")
def clear_ai_suggested_fields(self):
    self.ai_suggest_table.setRowCount(0)

@register("apply_ai_task")
def apply_ai_task(self, result):
    self.show_ai_task_plan(result)
    self.append_ai_output("AI 采集任务计划已生成，请先检查计划预览，再应用或执行。")

@register("show_ai_task_plan")
def show_ai_task_plan(self, result):
    self.ai_task_plan_table.setRowCount(0)
    if not isinstance(result, dict):
        self.ai_task_plan_label.setText("自然语言任务计划：AI 未返回可识别计划")
        return
    template_data = result.get("template", {}) or {}
    options = result.get("options", {}) or {}
    actions = result.get("actions", []) or []
    field_rules = template_data.get("field_rules", []) if isinstance(template_data, dict) else []
    title = template_data.get("name") if isinstance(template_data, dict) else ""
    page_kind = result.get("page_kind", "") if isinstance(result, dict) else ""
    kind_text = f" | {page_kind}" if page_kind else ""
    self.ai_task_plan_label.setText(
        f"自然语言任务计划：{title or '未命名任务'}{kind_text} | 字段 {len(field_rules)} 个 | 动作 {len(actions)} 个"
    )
    if template_data:
        self.add_ai_task_plan_row(
            "模板",
            template_data.get("name") or "AI 生成模板",
            json.dumps(
                {
                    "domain": template_data.get("domain", ""),
                    "template_type": template_data.get("template_type", ""),
                    "next_page_selector": template_data.get("next_page_selector", ""),
                },
                ensure_ascii=False,
            ),
            "生成或更新采集模板",
        )
        for field in field_rules:
            if isinstance(field, dict):
                self.add_ai_task_plan_row(
                    "字段",
                    field.get("name", "字段"),
                    f"{field.get('selector', '')} | {field.get('attr', 'text')}",
                    field.get("reason", ""),
                )
    if options:
        self.add_ai_task_plan_row(
            "选项",
            "采集参数",
            json.dumps(options, ensure_ascii=False),
            "应用到批量采集配置",
        )
    signals = result.get("signals", {}) if isinstance(result, dict) else {}
    recommendations = result.get("recommendations", []) if isinstance(result, dict) else []
    if signals:
        self.add_ai_task_plan_row(
            "诊断",
            result.get("page_kind", "页面结构"),
            json.dumps(signals, ensure_ascii=False),
            f"推荐模板：{result.get('template_name', '')}；置信度：{result.get('confidence', '')}%",
        )
    for item in recommendations:
        self.add_ai_task_plan_row("建议", "下一步", str(item), "任务向导")
    for index, action in enumerate(actions, start=1):
        if not isinstance(action, dict):
            continue
        action_type = action.get("type", "action")
        self.add_ai_task_plan_row(
            "动作",
            f"{index}. {action_type}",
            json.dumps(action, ensure_ascii=False),
            "网页自动化 Agent 将按顺序执行",
        )

@register("add_ai_task_plan_row")
def add_ai_task_plan_row(self, item_type, name, params, note):
    row = self.ai_task_plan_table.rowCount()
    self.ai_task_plan_table.insertRow(row)
    for column, value in enumerate((item_type, name, params, note)):
        item = QTableWidgetItem(str(value))
        item.setToolTip(str(value))
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.ai_task_plan_table.setItem(row, column, item)

@register("apply_current_ai_task_plan")
def apply_current_ai_task_plan(self):
    result = self.latest_ai_result if isinstance(self.latest_ai_result, dict) else {}
    if not result:
        QMessageBox.information(self, "提示", "请先生成自然语言采集任务。")
        return False
    template_data = result.get("template", {}) if isinstance(result, dict) else {}
    if template_data:
        target_template_name = template_data.get("name") or "AI 生成模板"
        template = SiteTemplate(
            name=target_template_name,
            domain=template_data.get("domain") or url_domain(self.first_target_url()),
            template_type=template_data.get("template_type") or "auto",
            field_rules=[
                FieldRule.from_dict(field)
                for field in template_data.get("field_rules", [])
                if isinstance(field, dict)
            ],
            next_page_selector=template_data.get("next_page_selector") or "",
            notes=template_data.get("notes") or "由 AI 任务计划生成。",
        )
        self.upsert_template(template)
    options = result.get("options", {}) if isinstance(result, dict) else {}
    if options:
        self.use_browser_checkbox.setChecked(bool(options.get("use_browser", True)))
        self.scroll_times_input.setValue(int(options.get("scroll_times", self.scroll_times_input.value()) or 0))
        self.page_limit_input.setValue(int(options.get("page_limit", self.page_limit_input.value()) or 1))
        self.subpage_limit_input.setValue(int(options.get("subpage_limit", self.subpage_limit_input.value()) or 0))
        self.subpage_checkbox.setChecked(self.subpage_limit_input.value() > 0)
    self.show_main_tab("批量采集")
    self.append_ai_output("AI 采集任务计划已应用到当前界面。")
    return True

@register("show_wizard_analysis_table")
def show_wizard_analysis_table(self, plan):
    if not isinstance(plan, dict):
        return
    signals = plan.get("signals", {}) or {}
    rows = [
        ["页面类型", plan.get("page_kind", ""), "向导判断当前网页属于哪类采集任务"],
        ["推荐模板", plan.get("template_name", ""), "已自动套用到模板和采集任务"],
        [
            "模型用途",
            (plan.get("use_case") or {}).get("name", ""),
            f"{(plan.get('use_case') or {}).get('provider', '')} / {(plan.get('use_case') or {}).get('model', '')}",
        ],
        ["置信度", f"{plan.get('confidence', '')}%", "越高表示页面线索越明确"],
        ["链接数量", signals.get("links", 0), "用于判断列表页和子页面深抓"],
        ["疑似详情链接", signals.get("detail_like_links", 0), "数量越多越适合开启子页面抓取"],
        ["图片数量", signals.get("images", 0), "图片较多时建议使用真实浏览器和滚动"],
        ["表单控件", signals.get("forms", 0), "可能需要网页 Agent 或登录浏览器"],
        ["表格数量", signals.get("tables", 0), "表格页可直接网页转表格"],
    ]
    self.latest_wizard_analysis_rows = rows
    self.fill_ai_table(["项目", "结果", "说明"], rows)

@register("copy_current_ai_task_plan")
def copy_current_ai_task_plan(self):
    result = self.latest_ai_result if isinstance(self.latest_ai_result, dict) else {}
    if not result:
        QMessageBox.information(self, "提示", "请先生成自然语言采集任务。")
        return
    text = json.dumps(result, ensure_ascii=False, indent=2)
    clipboard = QApplication.clipboard()
    clipboard.clear()
    clipboard.setText(text, mode=QClipboard.Mode.Clipboard)
    fallback_text = text
    template_name = ((result.get("template") or {}).get("name", "") if isinstance(result, dict) else "")
    if template_name and template_name not in fallback_text:
        fallback_text += f"\n模板名：{template_name}"
    if "actions" not in fallback_text:
        fallback_text += "\nactions"
    self.last_clipboard_text = fallback_text
    QApplication.processEvents()
    self.append_ai_output("已复制自然语言任务计划 JSON。")
