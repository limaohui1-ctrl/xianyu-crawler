"""Run archive table, detail, and reuse helpers."""

from ui_registry import register

import json

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox, QTableWidgetItem
from universal_core import normalize_url
from ui_firecrawl import firecrawl_summary_line

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
