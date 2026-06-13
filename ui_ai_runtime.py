"""AI settings runtime, health, provider overview, model, and key helpers."""

from ui_registry import register

import time

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QMessageBox, QLineEdit, QTableWidgetItem

from universal_core import (
    AI_PROVIDER_PRESETS,
    CollectorDatabase,
    ai_provider_runtime_overview,
    cleanup_user_data,
    diagnose_ai_settings,
    load_ai_settings,
    mask_api_key,
    model_tags,
    normalize_api_key_entries,
    record_recoverable_error,
    save_ai_settings,
    unique_model_names,
)


@register("load_ai_settings_to_ui")
def load_ai_settings_to_ui(self):
    settings = self.ai_settings
    self._loading_ai_settings = True
    provider = settings.get("provider") or "openai"
    provider_index = self.ai_provider_combo.findData(provider)
    self.ai_provider_combo.setCurrentIndex(max(0, provider_index))
    self.current_ai_provider = provider
    self.load_provider_settings_to_ui(settings)
    self._loading_ai_settings = False

@register("load_provider_settings_to_ui")
def load_provider_settings_to_ui(self, settings):
    format_index = self.ai_format_combo.findData(settings.get("api_format"))
    self.ai_format_combo.setCurrentIndex(max(0, format_index))
    self.ai_base_url_input.setText(settings.get("base_url", ""))
    self.ai_models_url_input.setText(settings.get("models_url", ""))
    if hasattr(self, "ai_model_search_input"):
        self.ai_model_search_input.clear()
    self.ai_model_cache = self.unique_models(
        (settings.get("model_cache") or []) + (settings.get("models") or [])
    )
    self.refresh_ai_model_combo(settings.get("model", ""))
    if hasattr(self, "ai_custom_model_input"):
        current_model = str(settings.get("model", "") or "").strip()
        cached_models = {str(item).strip() for item in (settings.get("model_cache") or []) + (settings.get("models") or [])}
        self.ai_custom_model_input.setText(current_model if current_model and current_model not in cached_models else "")
    self.ai_key_input.setText(settings.get("api_key", ""))
    self.ai_key_name_input.setText(settings.get("active_api_key_name", "") or "默认 Key")
    self.ai_key_entries = normalize_api_key_entries(
        settings.get("api_keys"),
        settings.get("api_key", ""),
        settings.get("active_api_key_name", ""),
    )
    if hasattr(self, "ai_search_provider_combo"):
        search_provider = settings.get("search_provider") or "serper"
        provider_index = self.ai_search_provider_combo.findData(search_provider)
        self.ai_search_provider_combo.setCurrentIndex(max(0, provider_index))
    if hasattr(self, "ai_search_api_key_input"):
        self.ai_search_api_key_input.setText(settings.get("search_api_key", ""))
    if hasattr(self, "ai_search_endpoint_input"):
        self.ai_search_endpoint_input.setText(settings.get("search_endpoint", ""))
    if hasattr(self, "ai_search_health_label"):
        self.ai_search_health_label.setText(self.search_health_summary_text(settings))
    if hasattr(self, "ai_auto_apply_use_case_checkbox"):
        self.ai_auto_apply_use_case_checkbox.setChecked(settings.get("auto_apply_use_case", True) is not False)
    self.refresh_ai_key_combo(settings.get("active_api_key_name", ""))
    self.update_ai_provider_boundary(settings)
    self.refresh_api_health_summary()
    self.refresh_ai_provider_overview()
    self.refresh_ai_repair_history()

@register("update_ai_provider_boundary")
def update_ai_provider_boundary(self, settings=None):
    if not hasattr(self, "ai_provider_boundary_label"):
        return
    provider = self.ai_provider_combo.currentData() if hasattr(self, "ai_provider_combo") else ""
    api_format = ""
    if isinstance(settings, dict):
        api_format = settings.get("api_format", "")
    elif hasattr(self, "ai_format_combo"):
        api_format = self.ai_format_combo.currentData() or ""
    preset_name = AI_PROVIDER_PRESETS.get(provider, {}).get("name", provider or "当前接口")
    is_extract_api = api_format == "thunderbit_extract" or provider == "thunderbit"
    if is_extract_api:
        self.ai_provider_boundary_label.setText(
            f"当前为第三方抽取接口：{preset_name} 负责网页抽取动作，不是通用大模型；模型/动作通常填写 extract。"
        )
        self.ai_model_search_input.setPlaceholderText("搜索动作，例如 extract")
        self.ai_model_combo.lineEdit().setPlaceholderText("第三方抽取接口动作名，例如 extract")
        if hasattr(self, "ai_fetch_models_button"):
            self.ai_fetch_models_button.setEnabled(False)
            self.ai_fetch_models_button.setText("无需拉取模型")
        if hasattr(self, "ai_model_count_label"):
            self.ai_model_count_label.setText(f"可选动作：{self.ai_model_combo.count()}")
    else:
        self.ai_provider_boundary_label.setText(
            f"当前为模型 API：{preset_name} 用于 AI 建议列、字段修复、自然语言任务和文件识别。"
        )
        self.ai_model_search_input.setPlaceholderText("搜索模型，例如 gpt / qwen / vision")
        self.ai_model_combo.lineEdit().setPlaceholderText("可选择模型，也可直接粘贴厂商文档里的模型名")
        if hasattr(self, "ai_fetch_models_button"):
            self.ai_fetch_models_button.setEnabled(True)
            self.ai_fetch_models_button.setText("拉取模型")

@register("unique_models")
def unique_models(self, models):
    return unique_model_names(models)

@register("clean_model_display_text")
def clean_model_display_text(self, text):
    text = str(text or "").strip()
    while text.startswith("[") and "]" in text:
        text = text.split("]", 1)[1].strip()
    return text

@register("current_ai_model_text")
def current_ai_model_text(self):
    current_text = self.ai_model_combo.currentText().strip()
    index = self.ai_model_combo.currentIndex()
    data = self.ai_model_combo.currentData() if index >= 0 else ""
    if data and current_text == self.ai_model_combo.itemText(index):
        return str(data).strip()
    return self.clean_model_display_text(current_text)

@register("api_health_summary_text")
def api_health_summary_text(self, diagnosis=None):
    diagnosis = diagnosis or diagnose_ai_settings(self.collect_ai_settings_from_ui())
    checks = diagnosis.get("checks", []) if isinstance(diagnosis, dict) else []
    error_count = sum(1 for row in checks if row.get("level") == "错误")
    confirm_count = sum(1 for row in checks if row.get("level") == "需确认")
    provider = self.ai_provider_combo.currentText() if hasattr(self, "ai_provider_combo") else ""
    model = self.current_ai_model_text() if hasattr(self, "ai_model_combo") else ""
    key_value = self.ai_key_input.text().strip() if hasattr(self, "ai_key_input") else ""
    key_name = self.ai_key_name_input.text().strip() if hasattr(self, "ai_key_name_input") else ""
    if not key_name and hasattr(self, "ai_key_combo"):
        key_name = self.ai_key_combo.currentData() or ""
    key_entry = next(
        (
            item for item in getattr(self, "ai_key_entries", [])
            if (key_name and item.get("name") == key_name) or (key_value and item.get("key") == key_value)
        ),
        {},
    )
    key_status = key_entry.get("status") or ("未测试" if key_value else "")
    if key_value:
        key_text = f"{key_name or '当前 Key'}/{key_status}/{mask_api_key(key_value)}"
    else:
        key_text = "未填写"
    if error_count:
        status = f"错误 {error_count} 项"
    elif confirm_count:
        status = f"需确认 {confirm_count} 项"
    else:
        status = "正常"
    return f"API 体检：{status}｜{provider}｜{model or '未选择模型'}｜Key {key_text}"

@register("search_health_summary_text")
def search_health_summary_text(self, settings=None):
    settings = settings or self.collect_ai_settings_from_ui()
    provider = settings.get("search_provider") or "serper"
    api_key = str(settings.get("search_api_key") or "").strip()
    endpoint = str(settings.get("search_endpoint") or "").strip()
    if not api_key:
        return f"搜索配置：未完成｜{provider}｜缺少搜索 API Key"
    if endpoint:
        return f"搜索配置：已填写｜{provider}｜自定义 Endpoint 已启用"
    return f"搜索配置：已填写｜{provider}｜使用默认 Endpoint"

@register("test_search_api_settings")
def test_search_api_settings(self):
    settings = self.collect_ai_settings_from_ui()
    message = self.search_health_summary_text(settings)
    if hasattr(self, "ai_search_health_label"):
        self.ai_search_health_label.setText(message)
    if not str(settings.get("search_api_key") or "").strip():
        QMessageBox.information(self, "搜索配置未完成", message)
        return False
    self.append_ai_output(f"搜索配置检测：{message}")
    QMessageBox.information(self, "搜索配置检测", message)
    return True

@register("refresh_api_health_summary")
def refresh_api_health_summary(self, diagnosis=None):
    if hasattr(self, "api_health_label"):
        self.api_health_label.setText(self.api_health_summary_text(diagnosis))
    if hasattr(self, "ai_search_health_label"):
        self.ai_search_health_label.setText(self.search_health_summary_text())
    settings = self.collect_ai_settings_from_ui() if hasattr(self, "ai_provider_combo") else {}
    if hasattr(self, "ai_primary_status_label"):
        model_ready = bool(str(settings.get("api_key") or "").strip() and str(settings.get("model") or "").strip())
        self.ai_primary_status_label.setText("主模型配置：已完成" if model_ready else "主模型配置：未完成")
    if hasattr(self, "ai_search_status_label"):
        search_ready = bool(str(settings.get("search_api_key") or "").strip())
        self.ai_search_status_label.setText("全网搜索增强：已启用" if search_ready else "全网搜索增强：未启用")
    if hasattr(self, "ai_advanced_status_label"):
        advanced_changed = bool(str(settings.get("models_url") or "").strip() or str(settings.get("base_url") or "").strip() or str(settings.get("api_format") or "").strip())
        self.ai_advanced_status_label.setText("高级接口设置：已自定义" if advanced_changed else "高级接口设置：使用默认")
    self.refresh_ai_setup_wizard()

@register("refresh_ai_provider_overview")
def refresh_ai_provider_overview(self):
    if not hasattr(self, "ai_provider_overview_table") or not hasattr(self, "ai_key_input"):
        return
    try:
        latest_settings = load_ai_settings()
    except Exception as exc:
        record_recoverable_error(
            "读取 AI 配置失败，已使用当前界面配置",
            exc,
            logger=self.append_ai_output,
        )
        latest_settings = self.ai_settings if isinstance(self.ai_settings, dict) else {}
    current_settings = self.collect_ai_settings_from_ui() if hasattr(self, "ai_provider_combo") else {}
    if isinstance(latest_settings, dict):
        providers = latest_settings.get("providers") or {}
        current_provider = current_settings.get("provider") or latest_settings.get("provider") or "openai"
        providers[current_provider] = {**providers.get(current_provider, {}), **current_settings}
        latest_settings["providers"] = providers
        latest_settings.update(providers.get(current_provider, {}))
        latest_settings["provider"] = current_provider
    rows = ai_provider_runtime_overview(latest_settings)
    table = self.ai_provider_overview_table
    table.blockSignals(True)
    table.setRowCount(0)
    for row_data in rows:
        row = table.rowCount()
        table.insertRow(row)
        online_text = row_data.get("models_url") or "手动/不支持"
        if row_data.get("models_updated_at"):
            online_text = f"{online_text}｜{row_data.get('models_updated_at')}"
        if row_data.get("models_refresh_error"):
            online_text = f"{online_text}｜失败：{row_data.get('models_refresh_error')}"
        connection_text = row_data.get("connection_status") or "未测试"
        if row_data.get("connection_tested_at"):
            connection_text = f"{connection_text}｜{row_data.get('connection_tested_at')}"
        if row_data.get("connection_error"):
            connection_text = f"{connection_text}｜{row_data.get('connection_error')}"
        values = [
            "是" if row_data.get("active") else "",
            row_data.get("provider_name", ""),
            row_data.get("config_status", ""),
            str(row_data.get("model_count", 0)),
            row_data.get("model", ""),
            f"{row_data.get('key_status', '')}｜{row_data.get('key_count', 0)} 个｜{row_data.get('active_key_name') or '未选择'}",
            row_data.get("api_format", ""),
            online_text,
            connection_text,
        ]
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setToolTip(
                "\n".join(
                    part for part in [
                        f"厂商：{row_data.get('provider_name', '')}",
                        f"Provider ID：{row_data.get('provider', '')}",
                        f"Base URL：{row_data.get('base_url', '')}",
                        f"当前 Key：{row_data.get('active_key_name') or '未选择'} {row_data.get('active_key_mask', '')}",
                        f"模型刷新：{row_data.get('models_updated_at') or '未刷新'} {row_data.get('models_refresh_error') or ''}",
                        f"连接测试：{row_data.get('connection_status') or '未测试'} {row_data.get('connection_tested_at') or ''} {row_data.get('connection_error') or ''}",
                        f"内置检查：{row_data.get('preset_status', '')} {row_data.get('issues', '')}",
                    ]
                    if part.strip()
                )
            )
            item.setData(Qt.ItemDataRole.UserRole, row_data.get("provider", ""))
            if row_data.get("active"):
                item.setBackground(QColor("#e6f4ff"))
            elif row_data.get("connection_status") == "失败":
                item.setBackground(QColor("#fff1f0"))
            elif row_data.get("config_status") == "错误":
                item.setBackground(QColor("#fff1f0"))
            elif row_data.get("config_status") == "需确认":
                item.setBackground(QColor("#fffbe6"))
            table.setItem(row, column, item)
    table.blockSignals(False)

@register("selected_ai_provider_from_overview")
def selected_ai_provider_from_overview(self):
    table = getattr(self, "ai_provider_overview_table", None)
    if not table:
        return ""
    selected = table.selectedIndexes()
    if not selected:
        return ""
    item = table.item(selected[0].row(), 0)
    return item.data(Qt.ItemDataRole.UserRole) if item else ""

@register("switch_ai_provider_from_overview_item")
def switch_ai_provider_from_overview_item(self, item):
    provider = item.data(Qt.ItemDataRole.UserRole) if item else ""
    self.switch_ai_provider_from_overview(provider)

@register("switch_ai_provider_from_overview")
def switch_ai_provider_from_overview(self, provider=None):
    if not isinstance(provider, str) or not provider:
        provider = self.selected_ai_provider_from_overview()
    if not provider:
        QMessageBox.information(self, "提示", "请先在厂商适配总览里选中一行。")
        return
    index = self.ai_provider_combo.findData(provider)
    if index < 0:
        QMessageBox.information(self, "提示", f"找不到厂商：{provider}")
        return
    self.ai_provider_combo.setCurrentIndex(index)
    self.append_ai_output(f"已切换到厂商：{self.ai_provider_combo.currentText()}")
    self.refresh_ai_provider_overview()

@register("model_display_text")
def model_display_text(self, model):
    provider = self.ai_provider_combo.currentData() if hasattr(self, "ai_provider_combo") else ""
    tags = model_tags(model, provider)
    prefix = " ".join(f"[{tag}]" for tag in tags)
    return f"{prefix} {model}".strip()

@register("refresh_ai_model_combo")
def refresh_ai_model_combo(self, selected_model=""):
    selected_model = selected_model or self.current_ai_model_text()
    query = self.ai_model_search_input.text().strip().lower() if hasattr(self, "ai_model_search_input") else ""
    visible_models = [
        model for model in self.ai_model_cache
        if not query
        or query in model.lower()
        or any(query in tag.lower() for tag in model_tags(model, self.ai_provider_combo.currentData() or ""))
    ]
    self.ai_model_combo.blockSignals(True)
    self.ai_model_combo.clear()
    for model in visible_models:
        self.ai_model_combo.addItem(self.model_display_text(model), model)
    selected_index = self.ai_model_combo.findData(selected_model)
    if selected_model and selected_index < 0:
        self.ai_model_combo.insertItem(0, self.model_display_text(selected_model), selected_model)
        selected_index = 0
    if selected_model:
        if selected_index >= 0:
            self.ai_model_combo.setCurrentIndex(selected_index)
        else:
            self.ai_model_combo.setCurrentText(selected_model)
    self.ai_model_combo.blockSignals(False)
    total = len(self.ai_model_cache)
    shown = len(visible_models)
    if hasattr(self, "ai_model_count_label"):
        if query:
            self.ai_model_count_label.setText(f"可选模型：{shown}/{total}")
        else:
            self.ai_model_count_label.setText(f"可选模型：{total}")
    self.update_ai_model_hint()
    self.update_ai_provider_boundary()

@register("update_ai_model_hint")
def update_ai_model_hint(self, *_args):
    if not hasattr(self, "ai_model_hint_label"):
        return
    model = self.current_ai_model_text()
    provider = self.ai_provider_combo.currentData() if hasattr(self, "ai_provider_combo") else ""
    if not model:
        self.ai_model_hint_label.setText("当前模型：未选择")
        return
    tags = model_tags(model, provider)
    if tags:
        self.ai_model_hint_label.setText(f"当前模型：{model}｜标签：{' / '.join(tags)}")
    else:
        self.ai_model_hint_label.setText(f"当前模型：{model}｜自定义/需按厂商文档确认")

@register("filter_ai_models")
def filter_ai_models(self):
    if getattr(self, "_loading_ai_settings", False):
        return
    self.refresh_ai_model_combo()

@register("refresh_ai_key_combo")
def refresh_ai_key_combo(self, selected_name=""):
    entries = normalize_api_key_entries(getattr(self, "ai_key_entries", []), self.ai_key_input.text().strip(), selected_name)
    self.ai_key_entries = entries
    selected_name = selected_name or self.ai_key_name_input.text().strip()
    self.ai_key_combo.blockSignals(True)
    self.ai_key_combo.clear()
    for entry in entries:
        status = entry.get("status") or "未测试"
        self.ai_key_combo.addItem(f"{entry['name']}｜{status}｜{mask_api_key(entry['key'])}", entry["name"])
    if selected_name:
        index = self.ai_key_combo.findData(selected_name)
        if index >= 0:
            self.ai_key_combo.setCurrentIndex(index)
    self.ai_key_combo.blockSignals(False)

@register("on_ai_key_selected")
def on_ai_key_selected(self):
    if getattr(self, "_loading_ai_settings", False):
        return
    selected_name = self.ai_key_combo.currentData()
    entry = next((item for item in getattr(self, "ai_key_entries", []) if item.get("name") == selected_name), None)
    if not entry:
        return
    self.ai_key_name_input.setText(entry.get("name", ""))
    self.ai_key_input.setText(entry.get("key", ""))
    self.refresh_api_health_summary()

@register("toggle_ai_key_visibility")
def toggle_ai_key_visibility(self):
    if self.ai_key_input.echoMode() == QLineEdit.EchoMode.Password:
        self.ai_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
        self.ai_key_show_button.setText("隐藏")
    else:
        self.ai_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.ai_key_show_button.setText("显示")

@register("add_or_update_ai_key")
def add_or_update_ai_key(self):
    name = self.ai_key_name_input.text().strip() or "默认 Key"
    key = self.ai_key_input.text().strip()
    if not key:
        QMessageBox.information(self, "提示", "请先填写 API Key。")
        return
    entries = [dict(item) for item in getattr(self, "ai_key_entries", [])]
    updated = False
    for entry in entries:
        if entry.get("name") == name:
            entry["key"] = key
            updated = True
            break
    if not updated:
        entries.append({"name": name, "key": key})
    self.ai_key_entries = normalize_api_key_entries(entries, "", name)
    self.refresh_ai_key_combo(name)
    self.ai_settings = save_ai_settings(self.collect_ai_settings_from_ui())
    self.append_ai_output(f"已保存 API Key：{name}（{mask_api_key(key)}）")
    self.refresh_api_health_summary()

@register("delete_current_ai_key")
def delete_current_ai_key(self):
    selected_name = self.ai_key_combo.currentData() or self.ai_key_name_input.text().strip()
    if not selected_name:
        return
    self.ai_key_entries = [
        dict(item) for item in getattr(self, "ai_key_entries", [])
        if item.get("name") != selected_name
    ]
    next_entry = self.ai_key_entries[0] if self.ai_key_entries else {"name": "", "key": ""}
    self.ai_key_name_input.setText(next_entry.get("name", ""))
    self.ai_key_input.setText(next_entry.get("key", ""))
    self.refresh_ai_key_combo(next_entry.get("name", ""))
    self.ai_settings = save_ai_settings(self.collect_ai_settings_from_ui())
    self.append_ai_output(f"已删除 API Key：{selected_name}")
    self.refresh_api_health_summary()

@register("confirm_cleanup_user_data")
def confirm_cleanup_user_data(self):
    message = (
        "将清理本机保存的 API Key、AI 调用日志、历史数据库、任务计划、变更提醒记录和浏览器登录态。\n\n"
        "模板库会保留；清理后需要重新填写 API Key 并重新登录需要登录态的网站。"
    )
    answer = QMessageBox.question(
        self,
        "清理本机数据",
        message,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if answer != QMessageBox.StandardButton.Yes:
        return
    result = cleanup_user_data(
        {
            "api_settings": True,
            "ai_logs": True,
            "history": True,
            "browser_profile": True,
            "templates": False,
        }
    )
    self.ai_settings = load_ai_settings()
    self.load_ai_settings_to_ui(self.ai_settings)
    self.database = CollectorDatabase()
    self.records = []
    self.refresh_history()
    self.refresh_run_archive()
    self.refresh_change_alerts()
    self.refresh_ai_call_log_tables()
    self.refresh_ai_repair_history_table()
    self.refresh_api_health_summary()
    removed_count = len(result.get("removed", []))
    failed = result.get("failed", [])
    if failed:
        QMessageBox.warning(self, "清理完成但有部分失败", f"已清理 {removed_count} 项。\n\n" + "\n".join(failed[:8]))
    else:
        QMessageBox.information(self, "清理完成", f"已清理 {removed_count} 项本机数据。")
    self.append_ai_output(f"已清理本机数据 {removed_count} 项。")

@register("update_current_ai_key_status")
def update_current_ai_key_status(self, status, error_text=""):
    name = self.ai_key_name_input.text().strip() or self.ai_key_combo.currentData() or "默认 Key"
    key = self.ai_key_input.text().strip()
    if not key:
        return
    entries = normalize_api_key_entries(getattr(self, "ai_key_entries", []), key, name)
    updated_entries = []
    found = False
    tested_at = time.strftime("%Y-%m-%d %H:%M:%S")
    for entry in entries:
        entry = dict(entry)
        if entry.get("name") == name:
            entry["key"] = key
            entry["status"] = status
            entry["last_tested_at"] = tested_at
            entry["last_error"] = str(error_text or "")[:500]
            found = True
        updated_entries.append(entry)
    if not found:
        updated_entries.append(
            {
                "name": name,
                "key": key,
                "status": status,
                "last_tested_at": tested_at,
                "last_error": str(error_text or "")[:500],
            }
        )
    self.ai_key_entries = updated_entries
    self.refresh_ai_key_combo(name)
    self.ai_settings = save_ai_settings(self.collect_ai_settings_from_ui())
    self.refresh_api_health_summary()

@register("switch_to_available_ai_key")
def switch_to_available_ai_key(self):
    entry = next((item for item in getattr(self, "ai_key_entries", []) if item.get("status") == "可用"), None)
    if not entry:
        QMessageBox.information(self, "提示", "还没有测试成功的可用 Key。")
        return
    self.ai_key_name_input.setText(entry.get("name", ""))
    self.ai_key_input.setText(entry.get("key", ""))
    self.refresh_ai_key_combo(entry.get("name", ""))
    self.ai_settings = save_ai_settings(self.collect_ai_settings_from_ui())
    self.append_ai_output(f"已切换到可用 Key：{entry.get('name')}（{mask_api_key(entry.get('key'))}）")
    self.refresh_api_health_summary()
