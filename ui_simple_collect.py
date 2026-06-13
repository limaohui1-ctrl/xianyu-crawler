"""Simple collect input, field, and one-click start helpers."""

from ui_registry import register

import json
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox, QHeaderView, QTableWidgetItem

from universal_core import (
    FieldRule,
    UniversalCollector,
    assess_record_completeness,
    compact_text,
    normalize_url,
)
from core_urls import (
    normalize_url,
)



@register("sync_simple_inputs_to_background")
def sync_simple_inputs_to_background(self):
    if hasattr(self, "simple_url_input"):
        text = self.simple_url_input.toPlainText().strip()
        if text:
            self.url_input.setPlainText(text)
            first_url = normalize_url(text.splitlines()[0]) if text.splitlines() else ""
            self.ai_url_input.setText(first_url)
    if hasattr(self, "simple_goal_input"):
        prompt = self.simple_goal_input.toPlainText().strip()
        if prompt:
            self.ai_prompt_input.setPlainText(prompt)
    if hasattr(self, "simple_status_label"):
        self.simple_status_label.setText("正在准备，后台会自动识别字段和页面")
    if hasattr(self, "simple_progress_label"):
        self.simple_progress_label.setText("后台：准备网址和采集需求")
    self.set_simple_flow_step("采集")
    self.refresh_simple_field_table()

@register("simple_input_lines")
def simple_input_lines(self):
    if not hasattr(self, "simple_url_input"):
        return []
    lines = []
    for line in self.simple_url_input.toPlainText().splitlines():
        value = line.strip().strip('"')
        if value:
            lines.append(value)
    return lines

@register("simple_target_kind")
def simple_target_kind(self, value):
    target = (value or "").strip().strip('"')
    lower_target = target.lower()
    file_exts = (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".txt", ".csv")
    if target and os.path.exists(target) and os.path.isfile(target):
        if lower_target.endswith(file_exts):
            return "file"
        return "unsupported_file"
    if lower_target.endswith((".pdf", ".png", ".jpg", ".jpeg", ".webp", ".bmp")):
        return "media_url"
    return "web_url"

@register("simple_prepare_file_extract")
def simple_prepare_file_extract(self, file_path):
    instruction = self.simple_goal_input.toPlainText().strip() if hasattr(self, "simple_goal_input") else ""
    if hasattr(self, "simple_status_label"):
        self.simple_status_label.setText("识别为本地文件，后台用 AI 转成表格")
    if hasattr(self, "simple_progress_label"):
        self.simple_progress_label.setText(f"后台：正在处理文件 {os.path.basename(file_path)}")
    self.set_simple_flow_step("采集")
    self.set_expert_mode(False)
    self.run_ai_worker(
        "extract_file",
        {
            "file_path": file_path,
            "instruction": instruction,
            "firecrawl_config": self.current_firecrawl_config(include_secret=True),
        },
    )
    return True

@register("simple_prepare_and_start_collect")
def simple_prepare_and_start_collect(self):
    self.sync_simple_inputs_to_background()
    lines = self.simple_input_lines()
    if lines:
        first_target = lines[0]
        target_kind = self.simple_target_kind(first_target)
        if target_kind == "file":
            return self.simple_prepare_file_extract(first_target)
        if target_kind == "unsupported_file":
            QMessageBox.information(self, "提示", "这个文件类型暂不支持一键采集，请换 PDF、图片、TXT 或 CSV。")
            return False
    if target_kind == "media_url" and hasattr(self, "simple_status_label"):
        self.simple_status_label.setText("识别为 PDF/图片网址，先按网页读取；需要 OCR 时请配置支持视觉的 API")
    self.set_expert_mode(False)
    return self.simple_start_collecting()

@register("simple_requested_field_names")
def simple_requested_field_names(self):
    prompt = self.simple_goal_input.toPlainText().strip() if hasattr(self, "simple_goal_input") else ""
    text = prompt.lower()
    candidates = [
        ("标题", ("标题", "title", "名称", "名字", "产品名", "商品名", "职位名", "公司名")),
        ("价格", ("价格", "price", "价钱", "售价", "薪资", "租金", "费用")),
        ("时间", ("时间", "date", "发布时间", "日期", "发布")),
        ("作者", ("作者", "author", "来源", "店铺", "公司", "联系人")),
        ("正文", ("正文", "body", "内容", "详情", "介绍", "描述", "参数")),
        ("图片", ("图片", "image", "img", "照片", "图")),
        ("链接", ("链接", "link", "url", "网址", "详情页")),
        ("表格", ("表格", "table")),
    ]
    names = []
    for name, tokens in candidates:
        if any(token.lower() in text for token in tokens):
            names.append(name)
    if not names:
        names = ["标题", "正文", "图片", "链接"]
    if "完整度" not in names:
        names.append("完整度")
    return names

@register("simple_has_ai_settings")
def simple_has_ai_settings(self):
    settings = self.collect_ai_settings_from_ui()
    base_url = str(settings.get("base_url") or "").strip().lower()
    api_key = str(settings.get("api_key") or "").strip()
    model = str(settings.get("model") or "").strip()
    if not base_url or not model:
        return False
    if api_key:
        return True
    return base_url.startswith(("http://127.0.0.1", "http://localhost"))

@register("simple_ai_field_rules_from_result")
def simple_ai_field_rules_from_result(self, result):
    fields = result.get("fields") if isinstance(result, dict) else result
    if not isinstance(fields, list):
        return []
    rules = []
    seen = set()
    for field in fields:
        if not isinstance(field, dict):
            continue
        name = compact_text(field.get("name") or "自定义字段", 40)
        if not name or name in seen:
            continue
        attr = str(field.get("attr") or "text").strip() or "text"
        if attr not in {"text", "href", "src", "content", "data-src"}:
            attr = "text"
        rules.append(
            FieldRule(
                name,
                str(field.get("selector") or "").strip(),
                attr,
                bool(field.get("multiple", False)),
            )
        )
        seen.add(name)
        if len(rules) >= 12:
            break
    return rules

@register("apply_simple_ai_fields")
def apply_simple_ai_fields(self, result):
    self.simple_ai_suggest_pending = False
    rules = self.simple_ai_field_rules_from_result(result)
    if not rules:
        self.simple_ai_field_rules = []
        self.refresh_simple_field_table()
        self.append_ai_output("普通首页 AI 未返回可用列，已继续使用本地规则。")
        return False
    self.simple_ai_field_rules = rules
    self.refresh_simple_field_table()
    if hasattr(self, "simple_status_label") and not self.worker:
        self.simple_status_label.setText(f"AI 已建议 {len(rules)} 列，可以确认并采集")
    self.append_ai_output(f"普通首页 AI 已建议 {len(rules)} 个字段，已自动更新按要求整理表。")
    return True

@register("simple_base_field_rules")
def simple_base_field_rules(self):
    if getattr(self, "simple_ai_field_rules", []):
        return list(self.simple_ai_field_rules)
    return [FieldRule(name, "") for name in self.simple_requested_field_names()]

@register("simple_visible_column_rules")
def simple_visible_column_rules(self):
    hidden = set(getattr(self, "simple_column_hidden", set()) or set())
    return [
        rule for rule in self.simple_base_field_rules()
        if getattr(rule, "name", "") and getattr(rule, "name", "") not in hidden
    ]

@register("simple_field_rules")
def simple_field_rules(self):
    base_rules = self.simple_visible_column_rules()
    filtered = []
    enabled = dict(getattr(self, "simple_column_enabled", {}) or {})
    for rule in base_rules:
        name = getattr(rule, "name", "")
        if not name:
            continue
        if enabled.get(name, True):
            filtered.append(rule)
    return filtered

@register("refresh_simple_column_cards")
def refresh_simple_column_cards(self, rules=None):
    if not hasattr(self, "simple_column_card_label"):
        return
    rules = rules if rules is not None else self.simple_field_rules()
    names = [rule.name for rule in rules or [] if getattr(rule, "name", "")]
    if not names:
        names = ["标题", "正文", "图片", "链接"]
    source = "AI 建议" if getattr(self, "simple_ai_field_rules", []) else "自动识别"
    self.simple_column_card_label.setText(f"{source}：" + "｜".join(names[:12]))
    if not hasattr(self, "simple_column_table"):
        return
    display_rules = self.simple_visible_column_rules()
    self._refreshing_simple_column_table = True
    try:
        self.simple_column_table.setRowCount(0)
        for rule in display_rules or []:
            name = getattr(rule, "name", "")
            if not name:
                continue
            row = self.simple_column_table.rowCount()
            self.simple_column_table.insertRow(row)
            enabled_item = QTableWidgetItem("")
            enabled_item.setFlags(
                (enabled_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                & ~Qt.ItemFlag.ItemIsEditable
            )
            checked = self.simple_column_enabled.get(name, True)
            enabled_item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            enabled_item.setData(Qt.ItemDataRole.UserRole, name)
            name_item = QTableWidgetItem(name)
            name_item.setToolTip(name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.simple_column_table.setItem(row, 0, enabled_item)
            self.simple_column_table.setItem(row, 1, name_item)
    finally:
        self._refreshing_simple_column_table = False

@register("on_simple_column_item_changed")
def on_simple_column_item_changed(self, item):
    if getattr(self, "_refreshing_simple_column_table", False) or not item or item.column() != 0:
        return
    name = item.data(Qt.ItemDataRole.UserRole)
    if not name:
        name_item = self.simple_column_table.item(item.row(), 1)
        name = name_item.text().strip() if name_item else ""
    if not name:
        return
    self.simple_column_enabled[name] = item.checkState() == Qt.CheckState.Checked
    self.refresh_simple_field_table()

@register("delete_selected_simple_columns")
def delete_selected_simple_columns(self):
    if not hasattr(self, "simple_column_table"):
        return False
    selected_rows = sorted({index.row() for index in self.simple_column_table.selectedIndexes()}, reverse=True)
    if not selected_rows and self.simple_column_table.currentRow() >= 0:
        selected_rows = [self.simple_column_table.currentRow()]
    deleted_names = []
    for row in selected_rows:
        item = self.simple_column_table.item(row, 1)
        name = item.text().strip() if item else ""
        if name:
            deleted_names.append(name)
            self.simple_column_hidden.add(name)
            self.simple_column_enabled.pop(name, None)
    if not deleted_names:
        self.simple_information("提示", "请先选中要删除的列。")
        return False
    self.refresh_simple_field_table()
    if hasattr(self, "simple_status_label"):
        self.simple_status_label.setText("已删除列：" + "、".join(deleted_names[:5]))
    return True

@register("maybe_start_simple_ai_suggest_fields")
def maybe_start_simple_ai_suggest_fields(self, urls):
    if not urls or not self.simple_has_ai_settings() or self.ai_worker:
        return False
    url = normalize_url(urls[0])
    if not url:
        return False
    goal = self.simple_goal_input.toPlainText().strip() if hasattr(self, "simple_goal_input") else ""
    try:
        html = UniversalCollector(logger=self.append_ai_output).fetch_static(url)
    except Exception as exc:
        self.append_ai_output(f"普通首页 AI 建议列读取网页失败，已用本地规则：{exc}")
        return False
    self.simple_ai_suggest_pending = True
    self.run_ai_worker("simple_suggest_fields", {"url": url, "html": html, "goal": goal})
    return True

@register("simple_field_value_text")
def simple_field_value_text(self, value):
    if isinstance(value, list):
        values = []
        for item in value:
            if isinstance(item, dict):
                values.append(item.get("url") or item.get("text") or json.dumps(item, ensure_ascii=False))
            else:
                values.append(str(item))
        return compact_text("；".join([item for item in values if item]), 1200)
    if isinstance(value, dict):
        return compact_text(json.dumps(value, ensure_ascii=False), 1200)
    return compact_text(str(value or ""), 1200)

@register("simple_field_status_text")
def simple_field_status_text(self, rules, rows):
    source = "AI 智能建议" if getattr(self, "simple_ai_field_rules", []) else "本地规则"
    field_count = len(rules or [])
    row_count = len(rows or [])
    if not row_count:
        return f"字段：{source}整理，已准备 {field_count} 列，采到结果后会自动填表"
    missing = []
    for index, rule in enumerate(rules or []):
        values = [row[index + 1] for row in rows if index + 1 < len(row)]
        if not any(str(value or "").strip() for value in values):
            missing.append(rule.name)
    if missing:
        missing_text = "、".join(missing[:6])
        if len(missing) > 6:
            missing_text += f"等 {len(missing)} 列"
        return f"字段：{source}整理，{field_count} 列，{row_count} 行；暂未抓到：{missing_text}"
    return f"字段：{source}整理，{field_count} 列，{row_count} 行；关键列都有内容"

@register("refresh_simple_field_table")
def refresh_simple_field_table(self):
    if not hasattr(self, "simple_field_table"):
        return
    rules = self.simple_field_rules()
    self.refresh_simple_column_cards(rules)
    columns = ["网址"] + [rule.name for rule in rules]
    table_rows = []
    for record in getattr(self, "records", []) or []:
        values = [record.get("url", "")]
        for rule in rules:
            values.append(self.simple_field_value_text(self.value_for_preview_rule(record, rule)))
        table_rows.append(values)
    self.simple_field_table.setRowCount(0)
    self.simple_field_table.setColumnCount(len(columns))
    self.simple_field_table.setHorizontalHeaderLabels(columns)
    for values in table_rows:
        row = self.simple_field_table.rowCount()
        self.simple_field_table.insertRow(row)
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setToolTip(str(value))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.simple_field_table.setItem(row, column, item)
    for column in range(len(columns)):
        mode = QHeaderView.ResizeMode.Stretch if column == len(columns) - 1 else QHeaderView.ResizeMode.ResizeToContents
        self.simple_field_table.horizontalHeader().setSectionResizeMode(column, mode)
    if hasattr(self, "simple_field_status_label"):
        self.simple_field_status_label.setText(self.simple_field_status_text(rules, table_rows))

@register("simple_field_table_data")
def simple_field_table_data(self):
    if not hasattr(self, "simple_field_table"):
        return [], []
    columns = []
    for column in range(self.simple_field_table.columnCount()):
        header = self.simple_field_table.horizontalHeaderItem(column)
        columns.append(header.text() if header else f"字段{column + 1}")
    rows = []
    for row in range(self.simple_field_table.rowCount()):
        values = []
        for column in range(self.simple_field_table.columnCount()):
            item = self.simple_field_table.item(row, column)
            values.append(item.text() if item else "")
        rows.append(values)
    return columns, rows

@register("simple_select_default_template")
def simple_select_default_template(self):
    if not hasattr(self, "template_combo"):
        return
    index = self.template_combo.findText("通用自动识别")
    if index >= 0:
        self.template_combo.setCurrentIndex(index)

@register("ensure_record_completeness")
def ensure_record_completeness(self, record, force=False):
    if not isinstance(record, dict):
        return record
    if not force and record.get("completeness_label") and "completeness_missing" in record:
        return record
    completeness = assess_record_completeness(record)
    record["completeness_score"] = completeness["score"]
    record["completeness_label"] = completeness["label"]
    record["completeness_missing"] = completeness["missing"]
    record["completeness_summary"] = completeness["summary"]
    return record

@register("simple_start_collecting")
def simple_start_collecting(self):
    if self.worker:
        self.append_log("已有采集任务正在运行，未重复启动。")
        return False
    urls = self.urls_from_input()
    if not urls:
        QMessageBox.information(self, "提示", "请先输入至少一个网址。")
        self.set_simple_flow_step("输入")
        return False
    self.simple_ai_field_rules = []
    self.simple_ai_suggest_pending = False
    self.clear_current_results()
    self.simple_merge_subpage_results = True
    self.simple_subpage_parent_map = {}
    self.url_input.setPlainText("\n".join(urls))
    if hasattr(self, "ai_url_input"):
        self.ai_url_input.setText(urls[0])
    depth_config = self.simple_collect_depth_config()
    self.simple_select_default_template()
    self.use_browser_checkbox.setChecked(True)
    self.page_limit_input.setValue(depth_config["page_limit"])
    self.scroll_times_input.setValue(max(depth_config["scroll_times"], self.scroll_times_input.value()))
    self.delay_input.setValue(max(1, self.delay_input.value()))
    self.keep_login_checkbox.setChecked(False)
    self.subpage_checkbox.setChecked(False)
    self.subpage_limit_input.setValue(0)
    self.selected_subpage_urls = []
    if hasattr(self, "simple_status_label"):
        self.simple_status_label.setText(f"正在{depth_config['label']}采集网页资料")
    if hasattr(self, "simple_progress_label"):
        self.simple_progress_label.setText(depth_config["progress"])
    self.set_simple_flow_step("采集")
    self.append_log(
        f"一键采集已启动：{depth_config['label']}模式，"
        f"补充最多 {depth_config['subpage_limit']} 个同站详情页。"
    )
    if self.maybe_start_simple_ai_suggest_fields(urls) and hasattr(self, "simple_status_label"):
        self.simple_status_label.setText("正在采集网页资料，AI 正在后台整理字段")
    self.start_collecting(
        skip_confirmation=True,
        runtime_overrides={
            "scrape_subpages": True,
            "subpage_limit": depth_config["subpage_limit"],
            "selected_subpage_urls": [],
            "simple_auto_subpages": True,
            "simple_collect_depth": depth_config["label"],
        },
    )
    return True
