"""Preview extraction, field value helpers, and pagination preview."""

from ui_registry import register

import json

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QMessageBox, QTableWidgetItem

from universal_core import (
    FieldRule,
    SiteTemplate,
    UniversalCollector,
    UniversalExtractor,
    compact_text,
    normalize_url,
    url_domain,
    record_recoverable_error,

)
from core_urls import (
    normalize_url,
    url_domain,
)



@register("preview_extract_current_page")
def preview_extract_current_page(self):
    url = self.first_target_url()
    if not url:
        QMessageBox.information(self, "提示", "请先输入网址。")
        return
    rules = self.suggested_field_rules_from_table()
    if not rules:
        rules = self.collect_field_rules_from_table()
    if not rules:
        QMessageBox.information(self, "提示", "请先 AI 建议列，或在高级采集里配置字段。")
        return
    try:
        html = self.fetch_snapshot_html(url) if self.use_browser_checkbox.isChecked() else UniversalCollector(logger=self.append_ai_output).fetch_static(url)
        template = SiteTemplate("AI 预采模板", field_rules=rules)
        record = UniversalExtractor(template).extract(html, url)
    except Exception as exc:
        QMessageBox.warning(self, "预采失败", str(exc))
        self.append_ai_output(f"预采失败：{exc}")
        return
    self.latest_preview_url = url
    self.latest_preview_html = html
    self.latest_preview_rules = rules
    self.show_preview_record(record, rules)
    self.append_ai_output(f"已预采 1 页：{url}")

@register("value_for_preview_rule")
def value_for_preview_rule(self, record, rule):
    aliases = {
        "标题": "title",
        "价格": "price",
        "时间": "published_time",
        "作者": "author",
        "正文": "body",
        "图片": "images",
        "链接": "links",
        "表格": "tables",
        "完整度": "completeness_label",
        "缺少资料": "completeness_missing",
    }
    key = aliases.get(rule.name)
    if key:
        return record.get(key, "")
    body = record.get("body", "")
    marker = "自定义字段："
    if marker in body:
        try:
            custom_json = body.split(marker, 1)[1].strip()
            custom_values = json.loads(custom_json)
            return custom_values.get(rule.name, "")
        except Exception as exc:
            record_recoverable_error(
                "解析预采自定义字段失败，已留空该字段",
                exc,
                details={"rule": rule.name},
            )
            return ""
    return ""

@register("show_preview_record")
def show_preview_record(self, record, rules):
    columns = ["网址"] + [rule.name for rule in rules]
    row = [record.get("url", "")]
    preview_values = {}
    for rule in rules:
        value = self.value_for_preview_rule(record, rule)
        preview_values[rule.name] = value
        if isinstance(value, (list, dict)):
            value = json.dumps(value, ensure_ascii=False)
        row.append(value)
    self.fill_ai_table(columns, [row])
    issues = self.analyze_preview_quality(rules, preview_values)
    self.latest_quality_issues = issues
    self.fill_quality_table(issues)

@register("ai_repair_problem_fields")
def ai_repair_problem_fields(self):
    rules = self.latest_preview_rules or self.suggested_field_rules_from_table()
    issues = self.secondary_repair_issues or [
        issue for issue in (self.latest_quality_issues or [])
        if issue.get("status") in ("需处理", "需确认")
    ]
    url = self.latest_preview_url or self.first_target_url()
    html = self.latest_preview_html
    if not url:
        QMessageBox.information(self, "提示", "请先输入网址并预采一页。")
        return
    if not rules:
        QMessageBox.information(self, "提示", "请先 AI 建议列，或在高级采集里配置字段。")
        return
    if not issues:
        QMessageBox.information(self, "提示", "当前没有需要修复的问题列。")
        return
    if not html:
        try:
            html = self.fetch_snapshot_html(url)
        except Exception as exc:
            QMessageBox.warning(self, "读取网页失败", str(exc))
            return
    self.repair_quality_before_issues = [dict(issue) for issue in issues]
    self.secondary_repair_issues = []
    self.fill_repair_quality_report_table([])
    self.auto_apply_repair_after_ai = True
    self.run_ai_worker(
        "repair_fields",
        {
            "url": url,
            "html": html,
            "field_rules": [rule.to_dict() for rule in rules],
            "quality_issues": issues,
            "goal": self.ai_prompt_input.toPlainText().strip(),
        },
    )

@register("preview_pagination_for_current_url")
def preview_pagination_for_current_url(self):
    url = self.first_target_url()
    if not url:
        QMessageBox.information(self, "提示", "请先输入网址。")
        return
    try:
        result = UniversalCollector(logger=self.append_ai_output).preview_pagination(
            url,
            next_page_selector=self.ai_next_page_selector_input.text().strip(),
            page_limit=self.ai_page_limit_input.value(),
            scroll_times=self.ai_scroll_times_input.value(),
            keep_login_state=self.keep_login_checkbox.isChecked(),
        )
    except Exception as exc:
        QMessageBox.warning(self, "分页预览失败", str(exc))
        self.append_ai_output(f"分页/滚动预览失败：{exc}")
        return
    self.show_pagination_preview(result.get("rows", []))
    self.append_ai_output(
        f"分页/滚动预览完成：{result.get('mode')}，将采集 {len(result.get('urls', []))} 个页面。"
    )

@register("show_pagination_preview")
def show_pagination_preview(self, rows):
    self.pagination_table.setRowCount(0)
    for source in rows:
        row = self.pagination_table.rowCount()
        self.pagination_table.insertRow(row)
        values = [
            source.get("page", row + 1),
            source.get("mode", ""),
            source.get("url", ""),
            source.get("scroll_times", ""),
            source.get("status", ""),
        ]
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setToolTip(str(value))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.pagination_table.setItem(row, column, item)

@register("apply_pagination_settings")
def apply_pagination_settings(self):
    selector = self.ai_next_page_selector_input.text().strip()
    page_limit = self.ai_page_limit_input.value()
    scroll_times = self.ai_scroll_times_input.value()
    self.next_page_selector_input.setText(selector)
    self.page_limit_input.setValue(page_limit)
    self.scroll_times_input.setValue(scroll_times)
    if selector:
        self.append_ai_output(f"已应用点击翻页：下一页 CSS={selector}，最多 {page_limit} 页。")
    else:
        self.append_ai_output(f"已应用无限滚动：同页滚动 {scroll_times} 次后采集。")
