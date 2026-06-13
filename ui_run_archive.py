"""Run archive table, detail, and reuse helpers."""

from ui_registry import register

import json
from copy import deepcopy

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QComboBox, QLabel, QListWidget, QListWidgetItem, QMessageBox, QTableWidgetItem
from universal_core import AI_MODEL_USE_CASE_PRESETS, normalize_url, search_template_market, template_market_items
from core_urls import normalize_url
from ui_firecrawl import firecrawl_summary_line

from universal_core import FieldRule, SiteTemplate

@register("fill_run_table")
def fill_run_table(self, runs):
    self.run_table.setRowCount(0)
    for run in runs:
        row = self.run_table.rowCount()
        self.run_table.insertRow(row)
        values = [
            run.get("id", ""),
            run.get("started_at", ""),
            run.get("finished_at", ""),
            self.run_status_text(run.get("status", "")),
            len(run.get("urls", []) or []),
            run.get("template_name", ""),
            run.get("ai_provider", ""),
            run.get("model", ""),
            run.get("result_count", 0),
        ]
        detail = json.dumps({"config": run.get("config", {}), "risks": run.get("risks", [])}, ensure_ascii=False)
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setToolTip(detail if column == 0 else str(value))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.run_table.setItem(row, column, item)

@register("selected_run_record")
def selected_run_record(self):
    selected_rows = sorted({index.row() for index in self.run_table.selectedIndexes()})
    if not selected_rows:
        return None
    row = selected_rows[0]
    id_item = self.run_table.item(row, 0)
    if not id_item:
        return None
    try:
        run_id = int(id_item.text())
    except ValueError:
        return None
    for run in self.run_records or []:
        if int(run.get("id") or 0) == run_id:
            return run
    self.run_records = self.database.recent_runs(1000)
    for run in self.run_records:
        if int(run.get("id") or 0) == run_id:
            return run
    return None

@register("update_run_detail")
def update_run_detail(self):
    run = self.selected_run_record()
    if not run:
        if hasattr(self, "run_detail_title_label"):
            self.run_detail_title_label.setText("未选择任务档案")
            self.run_detail_summary_output.clear()
            self.run_detail_url_table.setRowCount(0)
            self.run_detail_risk_table.setRowCount(0)
            self.run_detail_queue_table.setRowCount(0)
            self.run_detail_result_table.setRowCount(0)
            self.run_detail_json_output.clear()
        return
    config = run.get("config") or {}
    urls = run.get("urls") or config.get("urls") or []
    risks = run.get("risks") or []
    queue_snapshot = config.get("task_queue_snapshot") or []
    run_results = self.database.records_for_run(run.get("id"), 500)
    title = f"任务 #{run.get('id')} · {self.run_status_text(run.get('status')) or '未知状态'} · {run.get('template_name') or '未指定模板'}"
    self.run_detail_title_label.setText(title)
    summary_lines = [
        f"开始时间：{run.get('started_at', '')}",
        f"结束时间：{run.get('finished_at', '') or '未结束'}",
        f"结果数：{run.get('result_count', 0)}",
        f"已关联结果：{len(run_results)} 条",
        f"AI：{run.get('ai_provider', '') or config.get('ai_provider', '')} / {run.get('model', '') or config.get('model', '')}",
        f"浏览器：{'真实浏览器' if config.get('use_browser') else '普通请求'}",
        f"分页/滚动：最多 {config.get('page_limit', '')} 页，滚动 {config.get('scroll_times', '')} 次，间隔 {config.get('delay_seconds', '')} 秒",
        f"子页面：{'开启' if config.get('scrape_subpages') else '关闭'}，上限 {config.get('subpage_limit', 0)}",
        f"登录态：{'保留' if config.get('keep_login_state') else '不保留'}，跳过重复：{'开启' if config.get('skip_unchanged') else '关闭'}",
        f"队列快照：{len(queue_snapshot)} 项" + (f"，保存于 {config.get('task_queue_saved_at', '')}" if config.get("task_queue_saved_at") else ""),
    ]
    firecrawl_config = config.get("firecrawl") or {}
    firecrawl_summary = firecrawl_summary_line(firecrawl_config)
    if firecrawl_summary:
        summary_lines.append(firecrawl_summary)
    if run.get("notes"):
        summary_lines.append(f"备注：{run.get('notes')}")
    self.run_detail_summary_output.setPlainText("\n".join(summary_lines))
    self.run_detail_url_table.setRowCount(0)
    for url in urls:
        row = self.run_detail_url_table.rowCount()
        self.run_detail_url_table.insertRow(row)
        item = QTableWidgetItem(str(url))
        item.setToolTip(str(url))
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.run_detail_url_table.setItem(row, 0, item)
    self.run_detail_risk_table.setRowCount(0)
    risk_columns = ["级别", "检查项", "说明", "建议", "参考"]
    for risk in risks:
        row = self.run_detail_risk_table.rowCount()
        self.run_detail_risk_table.insertRow(row)
        for column, key in enumerate(risk_columns):
            value = risk.get(key, "")
            item = QTableWidgetItem(str(value))
            item.setToolTip(str(value))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if key == "级别" and value in ("高", "需处理"):
                item.setBackground(Qt.GlobalColor.red)
            elif key == "级别" and value == "需确认":
                item.setBackground(Qt.GlobalColor.yellow)
            self.run_detail_risk_table.setItem(row, column, item)
    self.fill_queue_snapshot_table(self.run_detail_queue_table, queue_snapshot, run_results)
    self.run_detail_result_table.setRowCount(0)
    for index, record in enumerate(run_results):
        self.add_record_to_table(self.run_detail_result_table, record, "run_detail", index)
    self.run_detail_json_output.setPlainText(
        json.dumps(
            {
                "config": config,
                "risks": risks,
                "task_queue_snapshot": queue_snapshot,
                "urls": urls,
                "result_count": len(run_results),
                "notes": run.get("notes", ""),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

@register("apply_run_config")
def apply_run_config(self, run):
    if not run:
        QMessageBox.information(self, "提示", "请先在任务档案表里选择一条记录。")
        return False
    config = run.get("config") or {}
    urls = config.get("urls") or run.get("urls") or []
    urls = [normalize_url(url) for url in urls if normalize_url(url)]
    if not urls:
        QMessageBox.information(self, "提示", "该任务档案没有可复用的网址。")
        return False
    self.url_input.setPlainText("\n".join(urls))
    template_name = config.get("template_name") or run.get("template_name") or ""
    if template_name:
        template_index = self.template_combo.findText(template_name)
        if template_index >= 0:
            self.template_combo.setCurrentIndex(template_index)
    self.use_browser_checkbox.setChecked(bool(config.get("use_browser", True)))
    self.scroll_times_input.setValue(int(config.get("scroll_times", self.scroll_times_input.value()) or 0))
    self.page_limit_input.setValue(int(config.get("page_limit", self.page_limit_input.value()) or 1))
    self.delay_input.setValue(int(config.get("delay_seconds", self.delay_input.value()) or 0))
    self.keep_login_checkbox.setChecked(bool(config.get("keep_login_state", False)))
    self.skip_unchanged_checkbox.setChecked(bool(config.get("skip_unchanged", True)))
    scrape_subpages = bool(config.get("scrape_subpages", False))
    self.subpage_checkbox.setChecked(scrape_subpages)
    self.subpage_limit_input.setValue(int(config.get("subpage_limit", self.subpage_limit_input.value()) or 0))
    self.selected_subpage_urls = list(config.get("selected_subpage_urls") or []) if scrape_subpages else []
    self.apply_firecrawl_config_to_ui(config.get("firecrawl", {}))
    if urls:
        self.ai_url_input.setText(urls[0])
        self.pick_url_input.setText(urls[0])
    provider = config.get("ai_provider") or run.get("ai_provider") or ""
    model = config.get("model") or run.get("model") or ""
    if provider:
        provider_index = self.ai_provider_combo.findData(provider)
        if provider_index >= 0:
            self.ai_provider_combo.setCurrentIndex(provider_index)
        if model:
            self.ai_model_combo.setCurrentText(model)
            self.save_ai_settings_from_ui()
    self.show_main_tab("批量采集")
    self.append_log(f"已复用任务档案 #{run.get('id')} 的网址、模板、分页、子页面、Firecrawl 和 AI 配置。")
    return True

@register("view_selected_run_queue_result")
def view_selected_run_queue_result(self):
    url = self.selected_queue_url(self.run_detail_queue_table)
    if not url:
        QMessageBox.information(self, "提示", "请先选择一个任务队列项。")
        return
    if not self.select_record_by_url(self.run_detail_result_table, url):
        QMessageBox.information(self, "提示", "当前任务结果里还没有这个队列项的结果。")
        return

@register("reuse_selected_run_config")
def reuse_selected_run_config(self):
    if self.apply_run_config(self.selected_run_record()):
        self.show_history_section("采集历史")

@register("rerun_selected_task")
def rerun_selected_task(self):
    if self.worker:
        QMessageBox.information(self, "提示", "已有采集任务正在运行，请稍后再重跑。")
        return
    run = self.selected_run_record()
    if self.apply_run_config(run):
        self.append_log(f"按任务档案 #{run.get('id')} 重新开始采集。")
        self.start_collecting()

@register("resumable_queue_urls_from_run")
def resumable_queue_urls_from_run(self, run):
    config = (run or {}).get("config") or {}
    queue_snapshot = config.get("task_queue_snapshot") or []
    urls = []
    seen = set()
    for source in queue_snapshot:
        status = source.get("status", "")
        url = normalize_url(source.get("url", ""))
        if not url or status not in ("失败", "运行中"):
            continue
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls

@register("resume_selected_run_queue")
def resume_selected_run_queue(self):
    if self.worker:
        QMessageBox.information(self, "提示", "已有采集任务正在运行，请稍后再继续任务。")
        return
    run = self.selected_run_record()
    if not run:
        QMessageBox.information(self, "提示", "请先在任务档案表里选择一条记录。")
        return
    urls = self.resumable_queue_urls_from_run(run)
    if not urls:
        QMessageBox.information(self, "提示", "该任务档案没有失败或未完成的队列项。")
        return
    if not self.apply_run_config(run):
        return
    self.url_input.setPlainText("\n".join(urls))
    self.append_log(f"继续任务档案 #{run.get('id')}：准备采集 {len(urls)} 个失败/未完成网址。")
    self.start_collecting()

@register("load_recent_records")
def load_recent_records(self):
    records = self.database.recent_records(200)
    self.history_records = records
    self.history_table.setRowCount(0)
    for index, record in enumerate(records):
        self.add_record_to_table(self.history_table, record, "history", index)
    self.run_records = self.database.recent_runs(100)
    self.fill_run_table(self.run_records)
    if hasattr(self, "change_alert_table"):
        self.refresh_change_alerts(silent=True)
    if self.run_records:
        self.run_table.selectRow(0)
    else:
        self.update_run_detail()
    self.refresh_overview()
    self.refresh_simple_recent_area()

@register("reload_templates")
def reload_templates(self):
    self.templates = self.template_store.load()
    self.template_combo.clear()
    self.template_list.clear()
    for template in self.templates:
        self.template_combo.addItem(template.name)
        item = QListWidgetItem(template.name)
        item.setToolTip(template.notes)
        self.template_list.addItem(item)
    if self.templates:
        self.template_list.setCurrentRow(0)
    if hasattr(self, "template_market_table"):
        self.refresh_template_market()

@register("refresh_template_market")
def refresh_template_market(self):
    if not hasattr(self, "template_market_table"):
        return
    query = self.template_market_search_input.text().strip() if hasattr(self, "template_market_search_input") else ""
    if self.template_market_category_combo.count() == 0:
        categories = sorted({item.get("category", "") for item in search_template_market() if item.get("category")})
        self.template_market_category_combo.blockSignals(True)
        self.template_market_category_combo.addItem("全部分类")
        for category in categories:
            self.template_market_category_combo.addItem(category)
        self.template_market_category_combo.blockSignals(False)
    category = self.template_market_category_combo.currentText() or "全部分类"
    items = search_template_market(query, category)
    self.template_market_items = items
    self.template_market_table.setRowCount(0)
    use_cases = AI_MODEL_USE_CASE_PRESETS
    for item in items:
        template = item.get("template") or SiteTemplate(item.get("name", ""))
        row = self.template_market_table.rowCount()
        self.template_market_table.insertRow(row)
        use_case = use_cases.get(item.get("recommended_use_case") or "web_scrape", {})
        values = [
            item.get("category", ""),
            template.name,
            len(template.field_rules),
            use_case.get("name", item.get("recommended_use_case", "")),
            template.notes,
        ]
        for column, value in enumerate(values):
            cell = QTableWidgetItem(str(value))
            cell.setToolTip(str(value))
            cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.template_market_table.setItem(row, column, cell)
    if items:
        self.template_market_table.selectRow(0)

@register("selected_market_template_item")
def selected_market_template_item(self):
    row = self.template_market_table.currentRow() if hasattr(self, "template_market_table") else -1
    if row < 0 or row >= len(getattr(self, "template_market_items", [])):
        return None
    return self.template_market_items[row]

@register("install_market_template")
def install_market_template(self, apply_to_task=False):
    item = self.selected_market_template_item()
    if not item:
        QMessageBox.information(self, "提示", "请先在模板市场里选择一个模板。")
        return False
    template = deepcopy(item.get("template") or SiteTemplate(item.get("name", "未命名模板")))
    self.upsert_template(template)
    use_case_key = item.get("recommended_use_case") or ""
    use_case_name = AI_MODEL_USE_CASE_PRESETS.get(use_case_key, {}).get("name", use_case_key)
    self.append_log(f"已从模板市场安装：{template.name}（推荐模型用途：{use_case_name}）")
    if apply_to_task:
        self.show_main_tab("批量采集")
        self.append_log(f"当前采集任务已使用模板：{template.name}")
    return True

@register("select_template_by_name")
def select_template_by_name(self, template_name):
    index = self.template_combo.findText(template_name)
    if index >= 0:
        self.template_combo.setCurrentIndex(index)
    list_items = self.template_list.findItems(template_name, Qt.MatchFlag.MatchExactly)
    if list_items:
        self.template_list.setCurrentItem(list_items[0])
    return index >= 0

@register("upsert_template")
def upsert_template(self, template):
    templates = list(getattr(self, "templates", []) or self.template_store.load())
    existing_index = next((index for index, saved in enumerate(templates) if saved.name == template.name), -1)
    if existing_index >= 0:
        templates[existing_index] = template
        target_index = existing_index
    else:
        templates.append(template)
        target_index = len(templates) - 1
    self.template_store.save(templates)
    self.reload_templates()
    self.template_list.setCurrentRow(max(0, target_index))
    self.select_template_by_name(template.name)
    return target_index

@register("load_template_to_editor")
def load_template_to_editor(self, row):
    if row < 0 or row >= len(self.templates):
        return
    template = self.templates[row]
    self.template_name_input.setText(template.name)
    self.template_domain_input.setText(template.domain)
    index = self.template_type_combo.findData(template.template_type)
    self.template_type_combo.setCurrentIndex(max(0, index))
    self.next_page_selector_input.setText(template.next_page_selector)
    self.template_notes_input.setPlainText(template.notes)
    self.field_table.setRowCount(0)
    for rule in template.field_rules:
        self.add_field_row(rule)

@register("add_field_row")
def add_field_row(self, rule=None):
    rule = rule or FieldRule("标题", "h1")
    row = self.field_table.rowCount()
    self.field_table.insertRow(row)
    self.field_table.setItem(row, 0, QTableWidgetItem(rule.name))
    self.field_table.setItem(row, 1, QTableWidgetItem(rule.selector))
    attr_combo = QComboBox()
    for attr in ("text", "href", "src", "content", "data-src"):
        attr_combo.addItem(attr)
    attr_index = attr_combo.findText(rule.attr)
    attr_combo.setCurrentIndex(max(0, attr_index))
    self.field_table.setCellWidget(row, 2, attr_combo)
    multi_check = QCheckBox()
    multi_check.setChecked(rule.multiple)
    self.field_table.setCellWidget(row, 3, multi_check)

@register("remove_selected_field")
def remove_selected_field(self):
    rows = sorted({index.row() for index in self.field_table.selectedIndexes()}, reverse=True)
    for row in rows:
        self.field_table.removeRow(row)
