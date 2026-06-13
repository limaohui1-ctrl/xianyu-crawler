"""Wizard configuration, new-user flow, two-click helpers."""

from ui_registry import register

from PyQt6.QtWidgets import QMessageBox

from universal_core import AI_PROVIDER_PRESETS, analyze_collect_task, normalize_url, scene_template_presets
from core_urls import normalize_url

from universal_core import SiteTemplate, UniversalCollector

@register("configure_collect_wizard")
def configure_collect_wizard(self):
    url = normalize_url(self.ai_url_input.text()) or self.first_target_url()
    if url:
        self.ai_url_input.setText(url)
        self.url_input.setPlainText(url)
        self.pick_url_input.setText(url)
    preset_name = self.wizard_scene_combo.currentText()
    if not scene_template_presets().get(preset_name):
        return
    html = ""
    if url and self.latest_preview_url == url and self.latest_preview_html:
        html = self.latest_preview_html
    elif url and os.environ.get("UNIVERSAL_COLLECTOR_SELF_TEST") != "1":
        try:
            if self.use_browser_checkbox.isChecked():
                html = self.fetch_snapshot_html(url)
            else:
                html = UniversalCollector(logger=self.append_ai_output).fetch_static(url)
            self.latest_preview_url = url
            self.latest_preview_html = html
        except Exception as exc:
            self.append_ai_output(f"向导读取页面失败，已改用网址和场景判断：{exc}")
    plan = analyze_collect_task(
        url,
        html=html,
        user_goal=self.ai_prompt_input.toPlainText().strip(),
        preferred_scene=preset_name,
    )
    self.latest_ai_result = plan
    preset = scene_template_presets().get(plan.get("template_name") or preset_name) or scene_template_presets().get(preset_name)
    template_index = self.scene_preset_combo.findText(preset.name)
    if template_index >= 0:
        self.scene_preset_combo.setCurrentIndex(template_index)
    self.apply_scene_preset()
    template_data = plan.get("template", {}) if isinstance(plan, dict) else {}
    options = plan.get("options", {}) if isinstance(plan, dict) else {}
    next_page_selector = template_data.get("next_page_selector") or preset.next_page_selector
    self.ai_next_page_selector_input.setText(next_page_selector or "")
    self.ai_page_limit_input.setValue(int(options.get("page_limit", self.ai_page_limit_input.value()) or 1))
    self.ai_scroll_times_input.setValue(int(options.get("scroll_times", self.ai_scroll_times_input.value()) or 0))
    if not self.ai_prompt_input.toPlainText().strip():
        self.ai_prompt_input.setPlainText(self.default_prompt_for_scene(preset))
    self.apply_pagination_settings()
    self.use_browser_checkbox.setChecked(bool(options.get("use_browser", self.use_browser_checkbox.isChecked())))
    self.subpage_limit_input.setValue(int(options.get("subpage_limit", self.subpage_limit_input.value()) or 0))
    self.subpage_checkbox.setChecked(self.subpage_limit_input.value() > 0)
    self.upsert_template(
        SiteTemplate(
            name=self.template_name_input.text().strip() or preset.name,
            domain=self.template_domain_input.text().strip().lower(),
            template_type=self.template_type_combo.currentData() or preset.template_type,
            field_rules=self.collect_field_rules_from_table(),
            next_page_selector=self.next_page_selector_input.text().strip(),
            notes=self.template_notes_input.toPlainText().strip(),
        )
    )
    self.show_ai_task_plan(plan)
    self.show_wizard_analysis_table(plan)
    self.apply_market_recommendation_from_plan(plan)
    self.apply_wizard_use_case(plan)
    preview_ok = self.run_wizard_preview(plan, html)
    self.show_main_tab("AI 抓取工作台")
    next_step = "字段质量已评分，可直接检查结果后开始采集。" if preview_ok else "下一步可点预采一页、AI 建议列或直接开始采集。"
    self.append_ai_output(
        f"向导已配置：{plan.get('summary', preset.name)}。{next_step}"
    )

@register("apply_advanced_ai_visibility")
def apply_advanced_ai_visibility(self):
    for box in getattr(self, "advanced_ai_boxes", []):
        layout = box.layout()
        if not layout:
            continue
        visible = box.isChecked()
        for index in range(layout.count()):
            item = layout.itemAt(index)
            widget = item.widget()
            if widget:
                widget.setVisible(visible)

@register("refresh_new_user_flow_status")
def refresh_new_user_flow_status(self, active_step="input"):
    if not hasattr(self, "new_user_flow_label"):
        return
    has_url = bool(self.first_target_url())
    has_plan = isinstance(getattr(self, "latest_ai_result", None), dict)
    has_records = bool(getattr(self, "records", []))
    if has_records and active_step in ("input", "prepared", "running"):
        active_step = "export"
    elif getattr(self, "worker", None):
        active_step = "running"
    elif has_plan and active_step == "input":
        active_step = "prepared"
    steps = [
        ("input", "1 输入网址", has_url),
        ("prepared", "2 AI 准备", has_plan),
        ("running", "3 开始采集", active_step == "running"),
        ("export", "4 导出结果", has_records),
    ]
    parts = []
    for key, label, done in steps:
        if key == active_step:
            marker = "进行中"
        elif done:
            marker = "完成"
        else:
            marker = "待办"
        parts.append(f"{label}：{marker}")
    self.new_user_flow_label.setText("新手流程：" + "  |  ".join(parts))
