"""Collection start, stop, run-archive, and finish helpers."""

from ui_registry import register

import time

from PyQt6.QtCore import QThread, Qt
from PyQt6.QtWidgets import QMessageBox, QTableWidgetItem

from universal_core import (
    CollectorDatabase,
    UniversalCollector,
    normalize_url,
)
from core_urls import (
    normalize_url,
)

from ui_firecrawl import firecrawl_start_log_line, firecrawl_summary_line
from ui_workers import CollectWorker

from core_database import CollectorDatabase


@register("start_collecting")
def start_collecting(self, skip_confirmation=False, runtime_overrides=None):
    runtime_overrides = runtime_overrides or {}
    if self.worker:
        self.append_log("已有采集任务正在运行，本次定时触发已跳过。")
        return
    urls = self.urls_from_input()
    if not urls:
        QMessageBox.information(self, "提示", "请先输入至少一个网址。")
        return
    risks = self.run_preflight_check()
    high_count = sum(1 for item in risks if item.get("级别") in ("高", "需处理"))
    if high_count:
        self.append_log("提示：检查结果包含高风险/需处理项，本次仍按当前配置继续。")
        self.collect_progress_label.setText(self.risk_summary_text(risks))
    if not skip_confirmation and not self.confirm_remaining_preflight_risks(risks):
        self.append_log("用户取消：开始前风险确认未通过，本次采集未启动。")
        self.collect_progress_label.setText("已取消：开始前风险确认未通过。")
        return
    if skip_confirmation:
        self.append_log(f"一键采集后台检查完成：{self.risk_summary_text(risks)}")
    if getattr(self, "_self_test_start_hook", None):
        self._self_test_start_hook(urls, risks)
        return
    scrape_subpages = bool(runtime_overrides.get("scrape_subpages", self.subpage_checkbox.isChecked()))
    subpage_limit = int(runtime_overrides.get("subpage_limit", self.subpage_limit_input.value()) or 0)
    skip_unchanged = bool(runtime_overrides.get("skip_unchanged", self.skip_unchanged_checkbox.isChecked()))
    self.current_run_strategy_label = runtime_overrides.get("simple_collect_depth", "") or self.simple_collect_depth_config().get("label", "")
    selected_subpage_urls = runtime_overrides.get(
        "selected_subpage_urls",
        self.selected_subpage_urls if self.subpage_checkbox.isChecked() else [],
    )
    follow_link_content = bool(runtime_overrides.get("follow_link_content", hasattr(self, "simple_follow_links_checkbox") and self.simple_follow_links_checkbox.isChecked()))
    follow_link_limit = int(runtime_overrides.get("follow_link_limit", self.simple_follow_links_limit_input.value() if hasattr(self, "simple_follow_links_limit_input") else 0) or 0)
    follow_same_site = bool(runtime_overrides.get("follow_same_site", hasattr(self, "simple_follow_same_site_checkbox") and self.simple_follow_same_site_checkbox.isChecked()))
    filter_pdf_media_links = bool(runtime_overrides.get("filter_pdf_media_links", hasattr(self, "simple_filter_pdf_media_checkbox") and self.simple_filter_pdf_media_checkbox.isChecked()))
    firecrawl_config = self.current_firecrawl_config(include_secret=True, runtime_overrides=runtime_overrides)
    self.fill_task_queue_table(self.estimated_task_queue(urls, runtime_overrides))
    self.refresh_new_user_flow_status("running")
    try:
        self.current_run_start_count = len(self.records)
        self.current_run_id = self.database.start_run(self.current_run_config(urls, runtime_overrides), risks)
        self.persist_current_run_queue_snapshot()
        self.update_collect_progress(
            {
                "processed": 0,
                "success": 0,
                "failed": 0,
                "total": len(self.estimated_task_queue(urls, runtime_overrides)),
                "current_url": urls[0] if urls else "",
                "status": "running",
            }
        )
        self.append_log(f"已保存任务运行档案：#{self.current_run_id}")
        firecrawl_log = firecrawl_start_log_line(firecrawl_config)
        if firecrawl_log:
            self.append_log(firecrawl_log)
        self.worker_thread = QThread(self)
        self.worker = CollectWorker(
            urls=urls,
            template_name=self.selected_template_name(),
            use_browser=self.use_browser_checkbox.isChecked(),
            scroll_times=self.scroll_times_input.value(),
            page_limit=self.page_limit_input.value(),
            delay_seconds=self.delay_input.value(),
            keep_login_state=self.keep_login_checkbox.isChecked(),
            skip_unchanged=skip_unchanged,
            scrape_subpages=scrape_subpages,
            subpage_limit=subpage_limit,
            selected_subpage_urls=selected_subpage_urls if scrape_subpages else [],
            follow_link_content=follow_link_content,
            follow_link_limit=follow_link_limit,
            follow_same_site=follow_same_site,
            filter_pdf_media_links=filter_pdf_media_links,
            run_id=self.current_run_id,
            firecrawl_config=firecrawl_config,
        )
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.log_signal.connect(self.append_log)
        self.worker.record_signal.connect(self.add_record)
        self.worker.progress_signal.connect(self.update_collect_progress)
        self.worker.finished_signal.connect(self.on_collect_finished)
        self.worker.finished_signal.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.append_log(f"开始采集 {len(urls)} 个网址。")
        self.set_collecting_buttons_state(True)
        self.worker_thread.start()
    except Exception as exc:
        failed_run_id = self.current_run_id
        if failed_run_id:
            try:
                self.database.finish_run(failed_run_id, status="failed", result_count=0, notes=f"采集启动失败：{exc}")
            except Exception as finish_exc:
                self.append_log(f"采集启动失败，且写入失败状态也失败：{finish_exc}")
        self.worker = None
        self.worker_thread = None
        self.current_run_id = None
        self.active_schedule_id = ""
        self.set_collecting_buttons_state(False)
        self.refresh_new_user_flow_status("prepared")
        self.append_log(f"采集启动失败：{exc}")
        QMessageBox.warning(self, "采集启动失败", str(exc))

@register("open_login_browser")
def open_login_browser(self):
    url = normalize_url(self.pick_url_input.text())
    if not url:
        urls = self.urls_from_input()
        url = urls[0] if urls else "https://example.com/"
    self.append_log(f"正在打开登录浏览器：{url}")
    try:
        UniversalCollector(logger=self.append_log).open_login_browser(url)
    except Exception as exc:
        QMessageBox.warning(self, "打开失败", str(exc))
        return
    self.keep_login_checkbox.setChecked(True)
    self.append_log("登录浏览器已打开。登录完成后关闭浏览器，之后采集会复用该登录状态。")

@register("stop_collecting")
def stop_collecting(self):
    if self.worker:
        self.worker.stop()
        self.set_collecting_buttons_state(True)
        if hasattr(self, "simple_status_label"):
            self.simple_status_label.setText("正在停止采集，已采到的结果会保留")
        if hasattr(self, "simple_progress_label"):
            self.simple_progress_label.setText("后台：正在安全停止，请稍等当前网页返回")
        self.append_log("正在停止采集。")

@register("on_collect_finished")
def on_collect_finished(self, summary=None):
    summary = summary or {}
    self.set_collecting_buttons_state(False)
    result_count = max(0, len(self.records) - int(self.current_run_start_count or 0))
    status = summary.get("status") or "finished"
    if status not in ("finished", "stopped", "failed", "partial"):
        status = "finished"
    notes = summary.get("notes") or f"采集完成，新增结果 {result_count} 条。"
    if result_count != int(summary.get("emitted_count") or result_count):
        notes = f"{notes}\n界面新增结果 {result_count} 条。"
    progress = self.current_run_progress or {}
    if progress:
        notes = (
            f"{notes}\n进度摘要：已处理 {int(progress.get('processed') or 0)}，"
            f"成功 {int(progress.get('success') or 0)}，失败 {int(progress.get('failed') or 0)}。"
        )
    try:
        self.database.finish_run(
            self.current_run_id,
            status=status,
            result_count=result_count,
            notes=notes,
        )
    except Exception as exc:
        self.append_log(f"写入任务结束状态失败：{exc}")
    if self.active_schedule_id:
        schedule_status = "完成" if status == "finished" else f"结束：{status}"
        try:
            self.mark_schedule_run(self.active_schedule_id, schedule_status, notes, count_run=True)
        except Exception as exc:
            self.append_log(f"写入计划运行状态失败：{exc}")
        self.active_schedule_id = ""
    final_progress = dict(progress)
    final_progress["status"] = status
    if final_progress:
        self.update_collect_progress(final_progress)
    finished_run_id = self.current_run_id
    self.worker = None
    self.worker_thread = None
    self.current_run_id = None
    self.current_run_strategy_label = ""
    if finished_run_id:
        self.current_run_id = finished_run_id
        try:
            self.persist_current_run_queue_snapshot()
        except Exception as exc:
            self.append_log(f"保存任务队列快照失败：{exc}")
        finally:
            self.current_run_id = None
    if self.maybe_continue_strategy_dual_run(status):
        return
    self.load_recent_records()
    alert_count = self.refresh_change_alerts(silent=True, notify=True)
    if alert_count:
        self.append_log(f"变更提醒已更新：当前 {alert_count} 条。")
    self.append_log(f"采集任务结束：{status}。")
    if hasattr(self, "simple_status_label"):
        self.simple_status_label.setText("采集完成，可以导出结果" if self.records else "采集结束，未得到结果")
    self.set_simple_flow_step("导出" if self.records else "输入")
    self.refresh_simple_result_summary()
    self.refresh_simple_recent_area()
    self.refresh_new_user_flow_status("export" if self.records else "prepared")
    self.fill_result_quality_table()
    self.finalize_strategy_dual_run_report()
