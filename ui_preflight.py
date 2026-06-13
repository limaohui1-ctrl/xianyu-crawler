"""URL input, import, config-build, and preflight-risk helpers."""

from ui_registry import register

import os
import time

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem

from universal_core import (
    assess_scrape_risks,
    mask_api_key,
    normalize_url,
    risk_confirmation_key,
    save_risk_confirmations,
)
from core_urls import (
    normalize_url,
)

from ui_export_utils import export_default_dir
from ui_firecrawl import apply_firecrawl_config_to_ui as apply_firecrawl_config_controls, current_firecrawl_config as current_firecrawl_config_from_ui


@register("urls_from_input")
def urls_from_input(self):
    urls = []
    for line in self.url_input.toPlainText().splitlines():
        url = normalize_url(line)
        if url:
            urls.append(url)
    return urls

def import_urls(self):
    file_path, _ = QFileDialog.getOpenFileName(
        self,
        "导入网址",
    export_default_dir(),
        "文本文件 (*.txt *.csv);;所有文件 (*.*)",
    )
    if not file_path:
        return
    with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
        urls = []
        for line in f:
            for part in line.replace(",", "\n").splitlines():
                if part.strip().startswith(("http://", "https://")):
                    urls.append(part.strip())
    self.url_input.setPlainText("\n".join(urls))
    self.append_log(f"已导入 {len(urls)} 个网址。")

@register("collect_preflight_risks")
def collect_preflight_risks(self):
    return assess_scrape_risks(
        self.urls_from_input(),
        use_browser=self.use_browser_checkbox.isChecked(),
        keep_login_state=self.keep_login_checkbox.isChecked(),
        delay_seconds=self.delay_input.value(),
        page_limit=self.page_limit_input.value(),
        scrape_subpages=self.subpage_checkbox.isChecked(),
        subpage_limit=self.subpage_limit_input.value(),
        field_rules=self.collect_field_rules_from_table(),
    )

@register("current_firecrawl_config")
def current_firecrawl_config(self, include_secret=True, runtime_overrides=None):
    return current_firecrawl_config_from_ui(
        self,
        include_secret=include_secret,
        runtime_overrides=runtime_overrides,
        mask_api_key_func=mask_api_key,
    )

@register("apply_firecrawl_config_to_ui")
def apply_firecrawl_config_to_ui(self, config):
    apply_firecrawl_config_controls(self, config)

@register("current_run_config")
def current_run_config(self, urls, runtime_overrides=None):
    runtime_overrides = runtime_overrides or {}
    scrape_subpages = bool(runtime_overrides.get("scrape_subpages", self.subpage_checkbox.isChecked()))
    subpage_limit = int(runtime_overrides.get("subpage_limit", self.subpage_limit_input.value()) or 0)
    skip_unchanged = bool(runtime_overrides.get("skip_unchanged", self.skip_unchanged_checkbox.isChecked()))
    selected_subpages = runtime_overrides.get(
        "selected_subpage_urls",
        self.selected_subpage_urls if self.subpage_checkbox.isChecked() else [],
    )
    follow_link_content = bool(runtime_overrides.get("follow_link_content", getattr(self, "simple_follow_links_checkbox", None).isChecked() if hasattr(self, "simple_follow_links_checkbox") else False))
    follow_link_limit = int(runtime_overrides.get("follow_link_limit", getattr(self, "simple_follow_links_limit_input", None).value() if hasattr(self, "simple_follow_links_limit_input") else 0) or 0)
    follow_same_site = bool(runtime_overrides.get("follow_same_site", getattr(self, "simple_follow_same_site_checkbox", None).isChecked() if hasattr(self, "simple_follow_same_site_checkbox") else True))
    filter_pdf_media_links = bool(runtime_overrides.get("filter_pdf_media_links", getattr(self, "simple_filter_pdf_media_checkbox", None).isChecked() if hasattr(self, "simple_filter_pdf_media_checkbox") else False))
    return {
        "urls": urls,
        "template_name": self.selected_template_name(),
        "use_browser": self.use_browser_checkbox.isChecked(),
        "scroll_times": self.scroll_times_input.value(),
        "page_limit": self.page_limit_input.value(),
        "delay_seconds": self.delay_input.value(),
        "keep_login_state": self.keep_login_checkbox.isChecked(),
        "skip_unchanged": skip_unchanged,
        "scrape_subpages": scrape_subpages,
        "subpage_limit": subpage_limit,
        "selected_subpage_urls": selected_subpages if scrape_subpages else [],
        "simple_auto_subpages": bool(runtime_overrides.get("simple_auto_subpages", False)),
        "simple_collect_depth": runtime_overrides.get("simple_collect_depth", ""),
        "follow_link_content": follow_link_content,
        "follow_link_limit": follow_link_limit,
        "follow_same_site": follow_same_site,
        "filter_pdf_media_links": filter_pdf_media_links,
        "firecrawl": self.current_firecrawl_config(include_secret=False, runtime_overrides=runtime_overrides),
        "ai_provider": self.ai_settings.get("provider", ""),
        "model": self.ai_settings.get("model", ""),
        "risk_checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

@register("run_preflight_check")
def run_preflight_check(self):
    risks = self.collect_preflight_risks()
    self.fill_risk_table(risks)
    high_count = sum(1 for item in risks if item.get("级别") in ("高", "需处理"))
    if high_count:
        self.append_log(f"抓取前检查完成：发现 {high_count} 个高风险/需处理项。")
    else:
        self.append_log("抓取前检查完成：未发现明显高风险配置。")
    return risks

@register("auto_fix_before_start")
def auto_fix_before_start(self):
    risks = self.run_preflight_check()
    fixes = []
    risk_items = {str(item.get("检查项", "")) for item in risks}
    urls = self.urls_from_input()

    if "网址" in risk_items:
        self.append_log("开始前自动修复：还没有网址，已保留当前配置，请先输入网址。")
        return False

    if self.keep_login_checkbox.isChecked():
        self.keep_login_checkbox.setChecked(False)
        fixes.append("关闭保留登录状态")

    if self.delay_input.value() < 1:
        self.delay_input.setValue(1)
        fixes.append("访问间隔调到 1 秒")

    scope = len(urls) * max(1, self.page_limit_input.value())
    if self.subpage_checkbox.isChecked():
        scope += len(urls) * max(0, self.subpage_limit_input.value())

    if scope > 50:
        if self.page_limit_input.value() > 10:
            self.page_limit_input.setValue(10)
            fixes.append("翻页上限降到 10 页")
        if self.subpage_checkbox.isChecked() and self.subpage_limit_input.value() > 10:
            self.subpage_limit_input.setValue(10)
            fixes.append("子页面上限降到 10 个")

    if self.use_browser_checkbox.isChecked():
        fixed_scope = len(urls) * max(1, self.page_limit_input.value())
        if self.subpage_checkbox.isChecked():
            fixed_scope += len(urls) * max(0, self.subpage_limit_input.value())
        if fixed_scope > 30:
            self.use_browser_checkbox.setChecked(False)
            fixes.append("大批量任务改为普通请求模式")

    if hasattr(self, "ai_page_limit_input"):
        self.ai_page_limit_input.setValue(self.page_limit_input.value())
    if hasattr(self, "ai_scroll_times_input"):
        self.ai_scroll_times_input.setValue(self.scroll_times_input.value())

    fixed_risks = self.run_preflight_check()
    self.fill_task_queue_table(self.estimated_task_queue(urls))
    summary = self.risk_summary_text(fixed_risks)
    if fixes:
        fix_text = "、".join(fixes)
        self.collect_progress_label.setText(f"开始前自动修复完成：{fix_text}。{summary}")
        self.append_log(f"开始前自动修复完成：{fix_text}。")
        self.append_ai_output(f"开始前自动修复完成：{fix_text}。{summary}")
    else:
        self.collect_progress_label.setText(f"开始前自动修复：没有可自动修改的安全项。{summary}")
        self.append_log("开始前自动修复：没有可自动修改的安全项。")
    return bool(fixes)

@register("remaining_confirmation_risks")
def remaining_confirmation_risks(self, risks):
    confirm_items = []
    for item in risks or []:
        level = item.get("级别", "")
        check_name = item.get("检查项", "")
        if level not in ("高", "需处理", "需确认"):
            continue
        if check_name in ("robots.txt", "敏感字段", "网址"):
            confirm_items.append(item)
    return confirm_items

@register("active_risk_confirmation_keys")
def active_risk_confirmation_keys(self, risks):
    urls = self.urls_from_input()
    now_ts = time.time()
    active_keys = set()
    changed = False
    states = dict(getattr(self, "risk_confirmations", {}) or {})
    for key, state in list(states.items()):
        try:
            expires_ts = time.mktime(time.strptime(state.get("expires_at", ""), "%Y-%m-%d %H:%M:%S"))
        except Exception:
            expires_ts = 0
        if expires_ts and expires_ts >= now_ts:
            active_keys.add(key)
        elif expires_ts:
            states.pop(key, None)
            changed = True
    if changed:
        self.risk_confirmations = save_risk_confirmations(states)
    return {
        risk_confirmation_key(urls, item)
        for item in self.remaining_confirmation_risks(risks)
        if risk_confirmation_key(urls, item) in active_keys
    }

@register("unconfirmed_preflight_risks")
def unconfirmed_preflight_risks(self, risks):
    confirmed_keys = self.active_risk_confirmation_keys(risks)
    urls = self.urls_from_input()
    return [
        item for item in self.remaining_confirmation_risks(risks)
        if risk_confirmation_key(urls, item) not in confirmed_keys
    ]

@register("remember_preflight_risk_confirmation")
def remember_preflight_risk_confirmation(self, risks, hours=24):
    urls = self.urls_from_input()
    states = dict(getattr(self, "risk_confirmations", {}) or {})
    confirmed_at = time.strftime("%Y-%m-%d %H:%M:%S")
    expires_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + int(hours or 24) * 3600))
    for item in self.remaining_confirmation_risks(risks):
        key = risk_confirmation_key(urls, item)
        states[key] = {
            "confirmed_at": confirmed_at,
            "expires_at": expires_at,
            "note": f"{item.get('检查项', '')}｜{item.get('说明', '')}",
        }
    self.risk_confirmations = save_risk_confirmations(states)
    return states

@register("confirm_remaining_preflight_risks")
def confirm_remaining_preflight_risks(self, risks):
    confirm_items = self.unconfirmed_preflight_risks(risks)
    if not confirm_items:
        return True
    if os.environ.get("UNIVERSAL_COLLECTOR_SELF_TEST") == "1":
        return True
    lines = []
    for item in confirm_items[:8]:
        level = item.get("级别", "需确认")
        name = item.get("检查项", "风险")
        detail = item.get("说明", "")
        advice = item.get("建议", "")
        lines.append(f"[{level}] {name}：{detail}\n建议：{advice}")
    if len(confirm_items) > 8:
        lines.append(f"还有 {len(confirm_items) - 8} 项风险未展开。")
    message = (
        "开始采集前还有需要你确认的风险项。\n\n"
        + "\n\n".join(lines)
        + "\n\n已能自动修复的访问频率、登录态和采集规模会由“开始前自动修复”处理；"
        "这些项目需要你确认来源、授权和站点规则。是否继续采集？"
    )
    answer = QMessageBox.question(
        self,
        "开始前风险确认",
        message,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if answer == QMessageBox.StandardButton.Yes:
        self.remember_preflight_risk_confirmation(confirm_items)
        return True
    return False

@register("risk_summary_text")
def risk_summary_text(self, risks):
    risks = risks or []
    counts = {}
    for item in risks:
        level = item.get("级别", "未知")
        counts[level] = counts.get(level, 0) + 1
    high_count = counts.get("高", 0) + counts.get("需处理", 0)
    confirm_count = counts.get("需确认", 0)
    normal_count = counts.get("正常", 0)
    checks = "、".join(
        dict.fromkeys(str(item.get("检查项", "")) for item in risks if item.get("检查项"))
    )
    if high_count:
        prefix = f"风险摘要：发现 {high_count} 个高风险/需处理项"
    elif confirm_count:
        prefix = f"风险摘要：有 {confirm_count} 个需确认项"
    elif normal_count:
        prefix = "风险摘要：基础检查正常"
    else:
        prefix = "风险摘要：等待抓取前检查"
    if checks:
        prefix += f"；涉及 {checks}"
    robots_refs = [item.get("参考", "") for item in risks if item.get("检查项") == "robots.txt" and item.get("参考")]
    if robots_refs:
        prefix += f"；先查看 robots.txt：{robots_refs[0]}"
    return prefix

@register("fill_risk_table")
def fill_risk_table(self, risks):
    columns = ["级别", "检查项", "说明", "建议", "参考"]
    self.risk_table.setRowCount(0)
    for source in risks:
        row = self.risk_table.rowCount()
        self.risk_table.insertRow(row)
        for column, key in enumerate(columns):
            value = source.get(key, "")
            item = QTableWidgetItem(str(value))
            item.setToolTip(str(value))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if key == "级别" and value in ("高", "需处理"):
                item.setBackground(Qt.GlobalColor.red)
            elif key == "级别" and value == "需确认":
                item.setBackground(Qt.GlobalColor.yellow)
            self.risk_table.setItem(row, column, item)
    if hasattr(self, "risk_summary_label"):
        self.risk_summary_label.setText(self.risk_summary_text(risks))

@register("selected_template_name")
def selected_template_name(self):
    return self.template_combo.currentText()
