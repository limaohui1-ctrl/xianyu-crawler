"""AI API test/diagnose/fetch and suggest/preview buttons."""

from ui_registry import register

from PyQt6.QtWidgets import QMessageBox

from universal_core import (
    classify_error,
    diagnose_ai_settings,
    load_ai_settings,
    record_recoverable_error,
    refresh_ai_provider_models,
    test_ai_provider_connectivity,
    AI_PROVIDER_PRESETS,

)


@register("test_ai_api")
def test_ai_api(self):
    if not self.ensure_ai_group_ready(need_search=False):
        return False
    self.run_ai_worker("test_api")
    return True

@register("diagnose_ai_api")
def diagnose_ai_api(self):
    self.run_ai_worker("diagnose_api")

@register("fetch_ai_models")
def fetch_ai_models(self):
    self.run_ai_worker("fetch_models")

@register("refresh_all_ai_provider_models")
def refresh_all_ai_provider_models(self):
    self.save_ai_settings_from_ui()
    self.run_ai_worker("refresh_provider_models", {"providers": list(AI_PROVIDER_PRESETS.keys())})

@register("test_all_ai_provider_connectivity")
def test_all_ai_provider_connectivity(self):
    self.save_ai_settings_from_ui()
    self.run_ai_worker("test_provider_connectivity", {"providers": list(AI_PROVIDER_PRESETS.keys())})

@register("ai_suggest_fields_for_current_url")
def ai_suggest_fields_for_current_url(self):
    if not self.ensure_ai_group_ready(need_search=False):
        return False
    url = self.first_target_url()
    if not url:
        QMessageBox.information(self, "提示", "请先输入网址。")
        return
    try:
        html = self.fetch_snapshot_html(url)
    except Exception as exc:
        QMessageBox.warning(self, "读取网页失败", str(exc))
        return
    self.run_ai_worker(
        "suggest_fields",
        {"url": url, "html": html, "goal": self.ai_prompt_input.toPlainText().strip()},
    )
