"""AI setup wizard: step tracking, refresh, advance, readiness grouping."""

from ui_registry import register

from PyQt6.QtWidgets import QMessageBox


@register("current_ai_setup_step")
def current_ai_setup_step(self):
    readiness = self.grouped_ai_readiness()
    if not readiness.get("model_ready"):
        return 1
    if not readiness.get("search_ready"):
        return 2
    return 3

@register("refresh_ai_setup_wizard")
def refresh_ai_setup_wizard(self):
    step = self.current_ai_setup_step()
    if hasattr(self, "advanced_ai_boxes"):
        for box in self.advanced_ai_boxes:
            box.setChecked(False)
    if hasattr(self, "ai_setup_wizard_label"):
        if step == 1:
            self.ai_setup_wizard_label.setText("配置向导：第 1 步，填写主模型配置并测试 API")
        elif step == 2:
            self.ai_setup_wizard_label.setText("配置向导：第 2 步，如需自然语言全网爬取，请补全搜索增强")
        else:
            self.ai_setup_wizard_label.setText("配置向导：已完成，你现在可以直接使用 AI 功能与自然语言全网爬取")
    if hasattr(self, "ai_setup_next_button"):
        self.ai_setup_next_button.setText("完成" if step >= 3 else "下一步")
    if hasattr(self, "ai_setup_finish_label"):
        if step == 1:
            self.ai_setup_finish_label.setText("完成主模型配置后，可直接使用主入口功能；字段修复等复杂步骤默认后台处理。")
        elif step == 2:
            self.ai_setup_finish_label.setText("补全搜索增强后，可直接使用自然语言全网爬取；搜索和整理会自动在后台串起来。")
        else:
            self.ai_setup_finish_label.setText("已完成：现在直接用主入口即可，复杂能力默认隐藏，需要时再展开。")
    return step

@register("advance_ai_setup_wizard")
def advance_ai_setup_wizard(self):
    step = self.current_ai_setup_step()
    if step == 1:
        self.save_ai_settings_from_ui()
        return self.test_ai_api()
    if step == 2:
        return self.test_search_api_settings()
    self.refresh_ai_setup_wizard()
    QMessageBox.information(self, "配置已完成", "AI 配置向导已完成，现在可以直接使用相关功能。")
    return True

@register("grouped_ai_readiness")
def grouped_ai_readiness(self):
    settings = self.collect_ai_settings_from_ui() if hasattr(self, "ai_provider_combo") else {}
    model_ready = bool(str(settings.get("api_key") or "").strip() and str(settings.get("model") or "").strip())
    search_ready = bool(str(settings.get("search_api_key") or "").strip())
    return {
        "model_ready": model_ready,
        "search_ready": search_ready,
        "settings": settings,
    }

@register("focus_ai_config_group")
def focus_ai_config_group(self, group_name):
    self.show_main_tab("AI 抓取工作台")
    if hasattr(self, "hero_status_label"):
        try:
            self.hero_status_label.setText(f"状态：请先完成 {group_name}")
        except RuntimeError:
            pass
    self.append_ai_output(f"请先完成：{group_name}")
    return group_name

@register("ensure_ai_group_ready")
def ensure_ai_group_ready(self, need_search=False):
    readiness = self.grouped_ai_readiness()
    if not readiness.get("model_ready"):
        self.focus_ai_config_group("主模型配置")
        QMessageBox.information(self, "主模型配置未完成", "请先在“主模型配置”里填写 API Key 和模型。")
        return False
    if need_search and not readiness.get("search_ready"):
        self.focus_ai_config_group("全网搜索增强")
        QMessageBox.information(self, "全网搜索增强未完成", "自然语言全网爬取还需要搜索 API Key，请先完成“全网搜索增强”。")
        return False
    return True
