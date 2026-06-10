import os
import sys
import traceback
import threading
import queue
import time
import json
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.request import Request, urlopen

from PyQt6.QtCore import QObject, QThread, QTimer, Qt, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QClipboard, QDesktopServices, QIcon, QPixmap, QColor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStyle,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from universal_core import (
    AI_CALL_LOG_FILE,
    AI_MODEL_USE_CASE_PRESETS,
    AI_PROVIDER_PRESETS,
    AI_SETTINGS_FILE,
    AIClient,
    APP_NAME_CN,
    APP_VERSION,
    CHANGE_ALERT_STATE_FILE,
    CollectorDatabase,
    DEFAULT_PAGE_LIMIT,
    DEFAULT_SCROLL_TIMES,
    DB_FILE,
    FIELD_HEADERS,
    FieldRule,
    RISK_CONFIRMATION_FILE,
    SELF_TEST_ERROR_LOG_FILE,
    SCHEDULE_FILE,
    SiteTemplate,
    STARTUP_LOG_FILE,
    TEMPLATE_TYPES,
    TEMPLATE_FILE,
    TemplateStore,
    UniversalCollector,
    UniversalExtractor,
    WebAgentExecutor,
    assess_record_completeness,
    analyze_collect_task,
    ai_provider_preset_health,
    ai_provider_runtime_overview,
    ai_extract_file_to_table,
    ai_parse_task,
    ai_repair_fields,
    ai_preset_for,
    ai_suggest_fields,
    ai_transform_records,
    append_ai_call_log,
    append_ai_repair_history,
    build_selector_from_clicked_element,
    change_alert_key,
    classify_error,
    clear_ai_call_logs,
    cleanup_user_data,
    compact_text,
    diagnose_ai_settings,
    download_images_from_records,
    ensure_runtime_dirs,
    extract_emails_and_phones,
    export_records,
    export_table_data,
    table_data_to_tsv,
    load_change_alert_states,
    load_risk_confirmations,
    load_ai_settings,
    load_ai_repair_history,
    load_ai_call_logs,
    mask_api_key,
    model_tags,
    normalize_api_key_entries,
    normalize_url,
    new_schedule_item,
    page_snapshot_from_html,
    recommend_template_market_items,
    runtime_self_test_error_log_file,
    runtime_startup_log_file,
    load_schedules,
    save_schedules,
    save_change_alert_states,
    save_risk_confirmations,
    schedule_next_run_text,
    save_ai_settings,
    refresh_ai_provider_models,
    test_ai_provider_connectivity,
    scene_template_presets,
    search_template_market,
    assess_scrape_risks,
    risk_confirmation_key,
    summarize_ai_call_logs,
    unique_model_names,
    url_domain,
)


class CollectWorker(QObject):
    log_signal = pyqtSignal(str)
    record_signal = pyqtSignal(dict)
    progress_signal = pyqtSignal(dict)
    finished_signal = pyqtSignal(dict)

    def __init__(
        self,
        urls,
        template_name,
        use_browser,
        scroll_times,
        page_limit,
        delay_seconds,
        keep_login_state,
        skip_unchanged,
        scrape_subpages,
        subpage_limit,
        selected_subpage_urls=None,
        run_id=0,
    ):
        super().__init__()
        self.urls = urls
        self.template_name = template_name
        self.use_browser = use_browser
        self.scroll_times = scroll_times
        self.page_limit = page_limit
        self.delay_seconds = delay_seconds
        self.keep_login_state = keep_login_state
        self.skip_unchanged = skip_unchanged
        self.scrape_subpages = scrape_subpages
        self.subpage_limit = subpage_limit
        self.selected_subpage_urls = selected_subpage_urls or []
        self.run_id = int(run_id or 0)
        self._stop_requested = False
        self._emitted_record_keys = set()

    def stop(self):
        self._stop_requested = True

    def should_stop(self):
        return self._stop_requested

    def record_key(self, record):
        if not isinstance(record, dict):
            return str(id(record))
        return "|".join(
            [
                str(record.get("run_id", "")),
                str(record.get("url", "")),
                str(record.get("fingerprint", "")),
                str(record.get("collected_at", "")),
            ]
        )

    def emit_record_once(self, record):
        key = self.record_key(record)
        if key in self._emitted_record_keys:
            return False
        self._emitted_record_keys.add(key)
        self.record_signal.emit(record)
        return True

    def emit_progress(self, progress):
        progress = dict(progress or {})
        progress["status"] = "running"
        self.progress_signal.emit(progress)

    @pyqtSlot()
    def run(self):
        emitted_count = 0
        error_text = ""
        try:
            collector = UniversalCollector(logger=self.log_signal.emit)
            original_save_record = collector.database.save_record

            def save_and_emit(record, *args, **kwargs):
                saved_record = original_save_record(record, *args, **kwargs)
                self.emit_record_once(record)
                return saved_record

            collector.database.save_record = save_and_emit
            results = collector.collect_urls(
                self.urls,
                template_name=self.template_name,
                use_browser=self.use_browser,
                scroll_times=self.scroll_times,
                page_limit=self.page_limit,
                delay_seconds=self.delay_seconds,
                keep_login_state=self.keep_login_state,
                skip_unchanged=self.skip_unchanged,
                scrape_subpages=self.scrape_subpages,
                subpage_limit=self.subpage_limit,
                selected_subpage_urls=self.selected_subpage_urls,
                stop_requested=self.should_stop,
                run_id=self.run_id,
                progress_callback=self.emit_progress,
            )
            total_count = len(results)
            for record in results:
                if self.emit_record_once(record):
                    emitted_count += 1
                failed_count = sum(1 for item in results[:emitted_count] if item.get("error"))
            emitted_count = len(self._emitted_record_keys)
            if total_count:
                self.progress_signal.emit(
                    {
                        "processed": total_count,
                        "success": total_count - sum(1 for item in results if item.get("error")),
                        "failed": sum(1 for item in results if item.get("error")),
                        "total": total_count,
                        "current_url": results[-1].get("url", ""),
                        "stage": "结果已回传",
                        "status": "running",
                    }
                )
        except Exception:
            error_text = traceback.format_exc()
            self.log_signal.emit(error_text)
        finally:
            if error_text:
                status = "partial" if emitted_count else "failed"
                notes = f"采集异常，已返回结果 {emitted_count} 条。\n{error_text}"
            elif self._stop_requested:
                status = "stopped"
                notes = f"用户停止采集，已返回结果 {emitted_count} 条。"
            else:
                status = "finished"
                notes = f"采集完成，已返回结果 {emitted_count} 条。"
            self.finished_signal.emit(
                {
                    "status": status,
                    "emitted_count": emitted_count,
                    "stopped": bool(self._stop_requested),
                    "error": error_text,
                    "notes": notes,
                }
            )


class RealScrapeCheckWorker(QObject):
    result_signal = pyqtSignal(dict)
    finished_signal = pyqtSignal()

    @pyqtSlot()
    def run(self):
        started = time.time()
        result = {
            "ok": False,
            "url": "https://example.com",
            "title": "",
            "body_preview": "",
            "link_count": 0,
            "row_count": 0,
            "error": "",
            "duration_ms": 0,
        }
        try:
            rows = UniversalCollector(logger=lambda _message: None).collect_urls(
                ["example.com"],
                template_name="通用自动识别",
                use_browser=True,
                page_limit=1,
                delay_seconds=0,
                skip_unchanged=False,
            )
            row = rows[0] if rows else {}
            title = row.get("title", "")
            body = row.get("body", "")
            error = row.get("error", "")
            result.update(
                {
                    "ok": bool(rows and title and body and not error),
                    "url": row.get("url", "https://example.com"),
                    "title": title,
                    "body_preview": compact_text(body, 120),
                    "link_count": len(row.get("links") or []),
                    "row_count": len(rows),
                    "error": error,
                }
            )
        except Exception as exc:
            result["error"] = str(exc)
        finally:
            result["duration_ms"] = int((time.time() - started) * 1000)
            self.result_signal.emit(result)
            self.finished_signal.emit()


class ImageDownloadWorker(QObject):
    log_signal = pyqtSignal(str)
    result_signal = pyqtSignal(list, str)
    finished_signal = pyqtSignal()

    def __init__(self, records, target_dir):
        super().__init__()
        self.records = records or []
        self.target_dir = target_dir

    @pyqtSlot()
    def run(self):
        saved = []
        try:
            saved = download_images_from_records(self.records, self.target_dir, logger=self.log_signal.emit)
        except Exception as exc:
            self.log_signal.emit(f"图片下载失败：{exc}")
            saved = [
                {
                    "status": "失败",
                    "file_path": "",
                    "image_url": "",
                    "source_title": "",
                    "source_url": "",
                    "size_bytes": "",
                    "error": str(exc),
                }
            ]
        finally:
            self.result_signal.emit(saved, self.target_dir)
            self.finished_signal.emit()


class AIWorker(QObject):
    log_signal = pyqtSignal(str)
    result_signal = pyqtSignal(str, object)
    finished_signal = pyqtSignal()

    def __init__(self, action, settings, payload):
        super().__init__()
        self.action = action
        self.settings = settings
        self.payload = payload or {}

    @pyqtSlot()
    def run(self):
        started = time.time()
        try:
            result = self.run_with_key_retry()
            self.write_call_log("成功", result=result, duration_ms=int((time.time() - started) * 1000))
            self.result_signal.emit(self.action, result)
        except Exception as exc:
            self.write_call_log("失败", error_text=str(exc), duration_ms=int((time.time() - started) * 1000))
            self.result_signal.emit(self.action, {"error": str(exc)})
        finally:
            self.finished_signal.emit()

    def run_action_once(self, settings):
        if self.action == "test_api":
            return AIClient(settings).test_connection()
        if self.action == "diagnose_api":
            return diagnose_ai_settings(settings)
        if self.action == "fetch_models":
            return AIClient(settings).fetch_models()
        if self.action == "refresh_provider_models":
            return refresh_ai_provider_models(settings, self.payload.get("providers"))
        if self.action == "test_provider_connectivity":
            return test_ai_provider_connectivity(settings, self.payload.get("providers"))
        if self.action in {"suggest_fields", "simple_suggest_fields"}:
            return ai_suggest_fields(
                self.payload.get("url", ""),
                self.payload.get("html", ""),
                self.payload.get("goal", ""),
                settings,
            )
        if self.action == "repair_fields":
            return ai_repair_fields(
                self.payload.get("url", ""),
                self.payload.get("html", ""),
                self.payload.get("field_rules", []),
                self.payload.get("quality_issues", []),
                self.payload.get("goal", ""),
                settings,
            )
        if self.action == "parse_task":
            return ai_parse_task(
                self.payload.get("prompt", ""),
                self.payload.get("snapshot", {}),
                settings,
            )
        if self.action == "transform_records":
            return ai_transform_records(
                self.payload.get("records", []),
                self.payload.get("instruction", ""),
                settings,
            )
        if self.action == "extract_file":
            return ai_extract_file_to_table(
                self.payload.get("file_path", ""),
                self.payload.get("instruction", ""),
                settings,
            )
        if self.action == "agent":
            return WebAgentExecutor(logger=self.log_signal.emit).execute(
                self.payload.get("url", ""),
                self.payload.get("actions", []),
                keep_login_state=bool(self.payload.get("keep_login_state", False)),
                headless=bool(self.payload.get("headless", True)),
            )
        raise RuntimeError(f"未知 AI 动作：{self.action}")

    def run_with_key_retry(self):
        try:
            return self.run_action_once(self.settings)
        except Exception as exc:
            if not self.should_retry_with_available_key(exc):
                raise
            fallback = self.available_fallback_key()
            if not fallback:
                raise
            retry_settings = dict(self.settings)
            retry_settings["api_key"] = fallback.get("key", "")
            retry_settings["active_api_key_name"] = fallback.get("name", "")
            self.log_signal.emit(f"当前 Key 可能不可用，已自动切换到可用 Key 重试：{fallback.get('name')}（{mask_api_key(fallback.get('key'))}）")
            result = self.run_action_once(retry_settings)
            if isinstance(result, dict):
                result = dict(result)
                result["_auto_switched_key"] = fallback.get("name", "")
            return result

    def should_retry_with_available_key(self, exc):
        if self.action in {"diagnose_api", "fetch_models", "agent"}:
            return False
        text = str(exc).lower()
        signals = [
            "401",
            "403",
            "unauthorized",
            "invalid api key",
            "invalid key",
            "quota",
            "insufficient",
            "rate limit",
            "rate_limit",
            "429",
            "额度",
            "限流",
            "余额",
            "欠费",
            "无效",
        ]
        return any(signal in text for signal in signals)

    def available_fallback_key(self):
        active_name = self.settings.get("active_api_key_name", "")
        active_key = self.settings.get("api_key", "")
        for entry in self.settings.get("api_keys", []) or []:
            if entry.get("status") != "可用":
                continue
            if entry.get("name") == active_name or entry.get("key") == active_key:
                continue
            if entry.get("key"):
                return entry
        return None

    def write_call_log(self, status, result=None, error_text="", duration_ms=0):
        result = result if isinstance(result, dict) else {}
        switched_name = result.get("_auto_switched_key", "")
        key_name = switched_name or self.settings.get("active_api_key_name", "")
        api_key = self.settings.get("api_key", "")
        if switched_name:
            fallback = next((item for item in self.settings.get("api_keys", []) or [] if item.get("name") == switched_name), {})
            api_key = fallback.get("key", api_key)
        append_ai_call_log(
            {
                "action": self.action,
                "status": status,
                "provider": self.settings.get("provider", ""),
                "provider_name": self.settings.get("provider_name", ""),
                "model": self.settings.get("model", ""),
                "key_name": key_name,
                "key_mask": mask_api_key(api_key),
                "duration_ms": int(duration_ms or 0),
                "auto_switched_key": switched_name,
                "error": str(error_text or "")[:1000],
            }
        )


class UniversalMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        ensure_runtime_dirs()
        self.setWindowTitle(f"{APP_NAME_CN} - {APP_VERSION}")
        self.resize(1280, 820)
        self.template_store = TemplateStore()
        self.database = CollectorDatabase()
        self.templates = self.template_store.load()
        self.records = []
        self.history_records = []
        self.worker_thread = None
        self.worker = None
        self.ai_thread = None
        self.ai_worker = None
        self.image_download_thread = None
        self.image_download_worker = None
        self.image_download_context = ""
        self.latest_image_download_rows = []
        self.real_scrape_check_thread = None
        self.real_scrape_check_worker = None
        self.ai_settings = load_ai_settings()
        self.schedule_timer = None
        self.schedule_tick_timer = None
        self.schedules = load_schedules()
        self.change_alert_states = load_change_alert_states()
        self.risk_confirmations = load_risk_confirmations()
        self.active_schedule_id = ""
        self.tray_icon = None
        self.last_unread_alert_notice_key = ""
        self.last_unread_alert_notice_count = 0
        self.notification_events = []
        self.last_clipboard_text = ""
        self.latest_ai_result = None
        self.latest_preview_url = ""
        self.latest_preview_html = ""
        self.latest_preview_rules = []
        self.latest_quality_issues = []
        self.repair_quality_before_issues = []
        self.repair_quality_report_rows = []
        self.repair_quality_sample_records = []
        self.secondary_repair_issues = []
        self.latest_market_recommendations = []
        self.simple_ai_field_rules = []
        self.simple_ai_suggest_pending = False
        self.simple_column_enabled = {}
        self.simple_column_hidden = set()
        self._refreshing_simple_column_table = False
        self.current_ai_repair_history_entry = None
        self.selected_subpage_urls = []
        self.change_alert_rows = []
        self.change_report_rows = []
        self.run_records = []
        self.task_queue_rows = []
        self.simple_merge_subpage_results = False
        self.simple_subpage_parent_map = {}
        self.low_quality_retry_baseline = {}
        self.low_quality_retry_active = False
        self.low_quality_retry_report_rows = []
        self.latest_crawl_discovery_messages = []
        self.last_real_scrape_check_result = {}
        self.current_run_id = None
        self.current_run_start_count = 0
        self.current_run_progress = {}
        self.current_run_strategy_label = ""
        self.latest_strategy_comparison_report = {}
        self.strategy_dual_run_active = False
        self.strategy_dual_run_ready_report = False
        self.strategy_dual_run_step = ""
        self.strategy_dual_run_urls = []
        self.strategy_dual_run_records_before = 0
        self.latest_wizard_analysis_rows = []
        self.auto_apply_repair_after_ai = False
        self._loading_ai_settings = False
        self.current_ai_provider = self.ai_settings.get("provider", "openai")
        self.ai_model_cache = []
        self._build_ui()
        self.setup_notification_tray()
        self.reload_templates()
        self.load_recent_records()
        self.start_schedule_tick()

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)

        self.tabs = QTabWidget()
        overview_tab = self.build_overview_tab()
        task_tab = self.build_task_tab()
        ai_tab = self.build_ai_tab()
        simple_tab = self.build_simple_collect_tab()
        self.tabs.addTab(simple_tab, "一键采集")
        self.tabs.addTab(overview_tab, "监控概览")
        self.tabs.addTab(ai_tab, "AI 抓取工作台")
        self.tabs.addTab(task_tab, "批量采集")
        self.tabs.addTab(self.build_template_tab(), "模板库")
        self.tabs.addTab(self.build_history_tab(), "历史与监控")
        self.expert_tab_names = ["监控概览", "AI 抓取工作台", "批量采集", "模板库", "历史与监控"]
        layout.addWidget(self.tabs)
        self.set_expert_mode(False)
        self.tabs.tabBar().hide()

        self.setCentralWidget(root)

    def set_tab_by_text(self, tab_widget, tab_text):
        if not tab_widget:
            return False
        for index in range(tab_widget.count()):
            if tab_widget.tabText(index) == tab_text:
                tab_widget.setCurrentIndex(index)
                return True
        return False

    def show_main_tab(self, tab_text):
        if tab_text != "一键采集" and tab_text in getattr(self, "expert_tab_names", []):
            self.set_expert_mode(False)
            return False
        return self.set_tab_by_text(getattr(self, "tabs", None), tab_text)

    def show_history_section(self, section_text):
        return False

    def set_expert_mode(self, enabled):
        self.expert_mode_enabled = False
        if not hasattr(self, "tabs"):
            return
        for index in range(self.tabs.count()):
            tab_name = self.tabs.tabText(index)
            if tab_name in getattr(self, "expert_tab_names", []):
                self.tabs.setTabVisible(index, False)
        self.set_tab_by_text(self.tabs, "一键采集")

    def toggle_expert_mode(self):
        self.set_expert_mode(False)

    def start_real_scrape_check(self):
        if self.real_scrape_check_thread:
            if hasattr(self, "simple_status_label"):
                self.simple_status_label.setText("真实自检正在运行")
            return False
        self.last_real_scrape_check_result = {}
        if hasattr(self, "simple_real_check_button"):
            self.simple_real_check_button.setEnabled(False)
            self.simple_real_check_button.setText("自检中")
        if hasattr(self, "simple_status_label"):
            self.simple_status_label.setText("正在真实自检：后台抓取 example.com")
        if hasattr(self, "simple_progress_label"):
            self.simple_progress_label.setText("真实自检：正在读取网页标题、正文和链接")
        self.real_scrape_check_thread = QThread(self)
        self.real_scrape_check_worker = RealScrapeCheckWorker()
        self.real_scrape_check_worker.moveToThread(self.real_scrape_check_thread)
        self.real_scrape_check_thread.started.connect(self.real_scrape_check_worker.run)
        self.real_scrape_check_worker.result_signal.connect(self.on_real_scrape_check_result)
        self.real_scrape_check_worker.finished_signal.connect(self.real_scrape_check_thread.quit)
        self.real_scrape_check_worker.finished_signal.connect(self.real_scrape_check_worker.deleteLater)
        self.real_scrape_check_thread.finished.connect(self.real_scrape_check_thread.deleteLater)
        self.real_scrape_check_thread.finished.connect(self.on_real_scrape_check_finished)
        self.real_scrape_check_thread.start()
        return True

    def on_real_scrape_check_result(self, result):
        result = dict(result or {})
        self.last_real_scrape_check_result = result
        if result.get("ok"):
            message = (
                f"真实自检通过：抓到 {result.get('row_count', 0)} 条，"
                f"标题《{compact_text(result.get('title', ''), 40)}》，"
                f"链接 {result.get('link_count', 0)} 个"
            )
            detail = f"真实自检：正文预览 {result.get('body_preview', '')}"
        else:
            error = result.get("error") or "没有抓到标题和正文"
            message = f"真实自检未通过：{compact_text(error, 80)}"
            detail = "真实自检：请检查网络、浏览器环境或目标网站限制"
        if hasattr(self, "simple_status_label"):
            self.simple_status_label.setText(message)
        if hasattr(self, "simple_progress_label"):
            self.simple_progress_label.setText(detail)
        log_message = (
            "真实自检结果："
            f"ok={bool(result.get('ok'))} rows={result.get('row_count', 0)} "
            f"title={result.get('title', '')} error={result.get('error', '')}"
        )
        if hasattr(self, "log_output"):
            self.log_output.append(log_message)
        if hasattr(self, "ai_output"):
            self.ai_output.appendPlainText(log_message)

    def on_real_scrape_check_finished(self):
        if hasattr(self, "simple_real_check_button"):
            self.simple_real_check_button.setEnabled(True)
            self.simple_real_check_button.setText("真实自检")
        self.real_scrape_check_thread = None
        self.real_scrape_check_worker = None

    def load_simple_ai_settings_to_ui(self):
        if not hasattr(self, "simple_ai_provider_combo"):
            return
        settings = self.ai_settings if isinstance(self.ai_settings, dict) else load_ai_settings()
        provider = settings.get("provider", "openai")
        provider_index = self.simple_ai_provider_combo.findData(provider)
        self.simple_ai_provider_combo.setCurrentIndex(max(0, provider_index))
        self.refresh_simple_ai_models(settings.get("model", ""))
        if hasattr(self, "simple_ai_key_input"):
            self.simple_ai_key_input.setText(settings.get("api_key", ""))

    def refresh_simple_ai_models(self, selected_model=""):
        if not hasattr(self, "simple_ai_model_combo"):
            return
        provider = self.simple_ai_provider_combo.currentData() or "openai"
        preset = ai_preset_for(provider)
        models = unique_model_names(preset.get("models", []))
        selected_model = selected_model or preset.get("default_model", "")
        self.simple_ai_model_combo.clear()
        for model in models:
            self.simple_ai_model_combo.addItem(model)
        if selected_model and self.simple_ai_model_combo.findText(selected_model) < 0:
            self.simple_ai_model_combo.insertItem(0, selected_model)
        model_index = self.simple_ai_model_combo.findText(selected_model)
        self.simple_ai_model_combo.setCurrentIndex(max(0, model_index))

    def on_simple_ai_provider_changed(self):
        self.refresh_simple_ai_models()

    def save_simple_ai_settings(self):
        provider = self.simple_ai_provider_combo.currentData() if hasattr(self, "simple_ai_provider_combo") else "openai"
        preset = ai_preset_for(provider)
        api_key = self.simple_ai_key_input.text().strip() if hasattr(self, "simple_ai_key_input") else ""
        model = self.simple_ai_model_combo.currentText().strip() if hasattr(self, "simple_ai_model_combo") else preset.get("default_model", "")
        settings = {
            "provider": provider,
            "provider_name": preset.get("name", provider),
            "api_format": preset.get("api_format", "openai_compatible"),
            "base_url": preset.get("base_url", ""),
            "models_url": preset.get("models_url", ""),
            "model": model,
            "api_key": api_key,
            "api_keys": normalize_api_key_entries([], api_key, "默认 Key") if api_key else [],
            "active_api_key_name": "默认 Key" if api_key else "",
        }
        self.ai_settings = save_ai_settings(settings)
        self.load_ai_settings_to_ui()
        if hasattr(self, "simple_status_label"):
            self.simple_status_label.setText(f"AI 设置已保存：{preset.get('name', provider)} / {model}")
        return True

    def test_simple_ai_settings(self):
        if not self.save_simple_ai_settings():
            return False
        self.test_ai_api()
        if hasattr(self, "simple_status_label"):
            self.simple_status_label.setText("正在测试 API，结果会自动显示")
        return True

    def simple_suggest_columns_now(self):
        self.sync_simple_inputs_to_background()
        urls = self.urls_from_input()
        if not urls:
            self.simple_information("提示", "请先粘贴一个网址。")
            return False
        if self.maybe_start_simple_ai_suggest_fields(urls):
            self.simple_status_label.setText("AI 正在建议列")
            return True
        self.simple_ai_field_rules = []
        self.refresh_simple_field_table()
        self.simple_status_label.setText("暂未配置 API，已用本地规则整理列")
        return True

    def simple_extract_contacts(self):
        records = self.records or self.database.recent_records(200)
        result = extract_emails_and_phones(records)
        rows = [
            [item.get("content", ""), item.get("type", ""), item.get("source_title", ""), item.get("source_url", "")]
            for item in result.get("rows", [])
        ]
        self.fill_ai_table(["内容", "类型", "来源标题", "来源网址"], rows)
        message = f"已提取邮箱 {len(result.get('emails', []))} 个、电话 {len(result.get('phones', []))} 个"
        self.simple_status_label.setText(message)
        self.simple_information("提取完成", message)
        return result

    def simple_download_images(self):
        records = self.records or self.database.recent_records(200)
        if not records:
            self.simple_information("提示", "没有可下载图片的采集结果。")
            return []
        target_dir = os.path.join(self.simple_export_dir(), "图片下载")
        if os.environ.get("UNIVERSAL_COLLECTOR_SELF_TEST") == "1":
            saved = download_images_from_records(records, target_dir, logger=self.append_ai_output)
            self.image_download_context = "simple"
            self.on_image_download_result(saved, target_dir)
            self.image_download_context = ""
            return saved
        self.start_image_download(records, target_dir, context="simple")
        return []

    def simple_add_schedule(self):
        self.sync_simple_inputs_to_background()
        item = self.add_schedule_from_current_config(minutes=30)
        if not item:
            return None
        self.simple_status_label.setText("定时监控已开启：每 30 分钟自动采集")
        self.simple_information("定时监控已开启", "软件会每 30 分钟按当前网址自动采集一次。")
        return item

    def simple_retry_failed_items(self):
        if self.worker:
            self.simple_status_label.setText("正在采集，请先等待当前任务结束")
            self.simple_information("提示", "正在采集，请先等待当前任务结束。")
            return False
        urls = self.incomplete_queue_urls()
        if not urls:
            self.simple_status_label.setText("当前没有失败网址可重试")
            self.simple_information("提示", "当前没有失败网址可重试。")
            return False
        self.simple_url_input.setPlainText("\n".join(urls))
        self.sync_simple_inputs_to_background()
        self.simple_status_label.setText(f"正在重试 {len(urls)} 个失败网址")
        self.simple_progress_label.setText("后台：只重试失败/未完成的网址，已成功的结果会保留")
        self.append_log(f"普通首页已准备重试 {len(urls)} 个失败/未完成网址。")
        self.start_collecting(skip_confirmation=True)
        return True

    def low_quality_records(self, records=None, limit=100):
        source_records = list(records if records is not None else (self.records or self.database.recent_records(limit)))
        weak_records = []
        required_missing = {"图片", "价格", "表格/规格"}
        seen_urls = set()
        for record in source_records:
            if not isinstance(record, dict):
                continue
            self.ensure_record_completeness(record)
            url = normalize_url(record.get("url", ""))
            if not url or url in seen_urls:
                continue
            score = int(record.get("completeness_score") or 0)
            missing = set(record.get("completeness_missing", []) or [])
            if score < 60 or missing.intersection(required_missing):
                weak_records.append(record)
                seen_urls.add(url)
        return weak_records

    def low_quality_urls(self, records=None, limit=100):
        urls = []
        for record in self.low_quality_records(records, limit):
            url = normalize_url(record.get("url", ""))
            if url and url not in urls:
                urls.append(url)
        return urls

    def low_quality_retry_queue(self, records=None, limit=100):
        queue_rows = []
        for record in self.low_quality_records(records, limit):
            url = normalize_url(record.get("url", ""))
            if not url:
                continue
            queue_rows.append(
                {
                    "enabled": True,
                    "url": url,
                    "title": compact_text(record.get("title") or "(无标题)", 80),
                    "completeness": record.get("completeness_label", ""),
                    "missing": "、".join(record.get("completeness_missing", []) or []),
                }
            )
        return queue_rows

    def low_quality_retry_baseline_for_urls(self, urls, records=None):
        selected_urls = {normalize_url(url) for url in urls or [] if normalize_url(url)}
        if not selected_urls:
            return {}
        baseline = {}
        for record in self.low_quality_records(records):
            url = normalize_url(record.get("url", ""))
            if not url or url not in selected_urls:
                continue
            self.ensure_record_completeness(record)
            baseline[url] = {
                "url": url,
                "title": record.get("title") or "(无标题)",
                "score": int(record.get("completeness_score") or 0),
                "label": record.get("completeness_label", ""),
                "missing": list(record.get("completeness_missing", []) or []),
            }
        return baseline

    def confirm_low_quality_retry_queue(self, queue_rows):
        self.last_low_quality_retry_queue = [dict(row) for row in queue_rows or []]
        if not queue_rows:
            return []
        if os.environ.get("UNIVERSAL_COLLECTOR_SELF_TEST") == "1":
            return [row.get("url", "") for row in queue_rows if row.get("enabled", True)]

        dialog = QDialog(self)
        dialog.setWindowTitle("重抓低完整度结果")
        dialog.resize(820, 420)
        layout = QVBoxLayout(dialog)
        summary = QLabel(f"将用完整模式重抓 {len(queue_rows)} 条低完整度结果。可取消不需要重抓的网址。")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        table = QTableWidget(0, 5)
        table.setHorizontalHeaderLabels(["重抓", "标题", "完整度", "缺少资料", "网址"])
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        for row_data in queue_rows:
            row = table.rowCount()
            table.insertRow(row)
            enabled_item = QTableWidgetItem("")
            enabled_item.setFlags((enabled_item.flags() | Qt.ItemFlag.ItemIsUserCheckable) & ~Qt.ItemFlag.ItemIsEditable)
            enabled_item.setCheckState(Qt.CheckState.Checked if row_data.get("enabled", True) else Qt.CheckState.Unchecked)
            table.setItem(row, 0, enabled_item)
            for column, key in enumerate(("title", "completeness", "missing", "url"), start=1):
                value = row_data.get(key, "")
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(row, column, item)
        layout.addWidget(table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return []
        selected_urls = []
        for row in range(table.rowCount()):
            enabled = table.item(row, 0)
            url_item = table.item(row, 4)
            if enabled and enabled.checkState() == Qt.CheckState.Checked and url_item:
                selected_urls.append(url_item.text())
        return selected_urls

    def simple_retry_low_quality_items(self):
        if self.worker:
            self.simple_status_label.setText("正在采集，请先等待当前任务结束")
            self.simple_information("提示", "正在采集，请先等待当前任务结束。")
            return False
        queue_rows = self.low_quality_retry_queue()
        urls = self.confirm_low_quality_retry_queue(queue_rows)
        urls = [normalize_url(url) for url in urls]
        urls = [url for index, url in enumerate(urls) if url and url not in urls[:index]]
        if not urls:
            self.simple_status_label.setText("当前没有低完整度结果需要重抓")
            self.simple_information("提示", "当前没有低完整度结果需要重抓。")
            return False
        self.low_quality_retry_baseline = self.low_quality_retry_baseline_for_urls(urls)
        self.low_quality_retry_active = True
        self.low_quality_retry_report_rows = []
        self.refresh_low_quality_retry_report_summary()
        complete_index = self.simple_depth_combo.findData("complete") if hasattr(self, "simple_depth_combo") else -1
        if complete_index >= 0:
            self.simple_depth_combo.setCurrentIndex(complete_index)
        depth_config = self.simple_collect_depth_config()
        self.simple_select_default_template()
        self.use_browser_checkbox.setChecked(True)
        self.page_limit_input.setValue(depth_config["page_limit"])
        self.scroll_times_input.setValue(max(depth_config["scroll_times"], self.scroll_times_input.value()))
        self.delay_input.setValue(max(1, self.delay_input.value()))
        self.simple_url_input.setPlainText("\n".join(urls))
        self.sync_simple_inputs_to_background()
        self.simple_status_label.setText(f"正在用完整模式重抓 {len(urls)} 条低完整度结果")
        self.simple_progress_label.setText("后台：低完整度结果会用完整深度重新采集，重点补图片、价格和规格")
        self.append_log(f"普通首页已准备重抓 {len(urls)} 条低完整度结果。")
        self.start_collecting(
            skip_confirmation=True,
            runtime_overrides={
                "scrape_subpages": True,
                "subpage_limit": depth_config["subpage_limit"],
                "selected_subpage_urls": [],
                "simple_auto_subpages": True,
                "simple_collect_depth": depth_config["label"],
                "skip_unchanged": False,
            },
        )
        return True

    def retry_report_captured_fields(self, before_missing, after_missing):
        before_set = set(before_missing or [])
        after_set = set(after_missing or [])
        captured = sorted(before_set - after_set)
        still_missing = sorted(after_set)
        return captured, still_missing

    def retry_report_summary_text(self):
        rows = list(getattr(self, "low_quality_retry_report_rows", []) or [])
        if not rows:
            return "重抓效果：暂无"
        total_delta = sum(int(row.get("delta") or 0) for row in rows)
        average_delta = int(total_delta / len(rows)) if rows else 0
        improved = sum(1 for row in rows if int(row.get("delta") or 0) > 0)
        captured_values = []
        still_missing_values = []
        for row in rows:
            captured_values.extend(row.get("captured_fields", []) or [])
            still_missing_values.extend(row.get("still_missing_fields", []) or [])
        captured_unique = list(dict.fromkeys(captured_values))[:4]
        still_missing_unique = list(dict.fromkeys(still_missing_values))[:4]
        captured_text = "、".join(captured_unique) if captured_unique else "暂无新增"
        still_missing_text = "、".join(still_missing_unique) if still_missing_unique else "无"
        return (
            f"重抓效果：已回收 {len(rows)} 条，提升 {improved} 条，平均 {average_delta:+d} 分；"
            f"补到 {captured_text}；仍缺 {still_missing_text}"
        )

    def refresh_low_quality_retry_report_summary(self):
        if hasattr(self, "simple_retry_report_label"):
            self.simple_retry_report_label.setText(self.retry_report_summary_text())

    def retry_report_table_data(self):
        columns = ["网址", "标题", "重抓前完整度", "重抓后完整度", "提升分数", "补到资料", "仍缺资料"]
        rows = []
        for row in getattr(self, "low_quality_retry_report_rows", []) or []:
            rows.append(
                [
                    row.get("url", ""),
                    row.get("title", ""),
                    row.get("before", 0),
                    row.get("after", 0),
                    row.get("delta", 0),
                    row.get("captured", ""),
                    row.get("still_missing", ""),
                ]
            )
        return columns, rows

    def simple_export_retry_report(self):
        columns, rows = self.retry_report_table_data()
        if not rows:
            self.simple_information("提示", "还没有重抓效果报告。请先使用“重抓低完整度”。")
            return False
        file_path = self.simple_export_filename("重抓效果报告")
        try:
            export_table_data(file_path, columns, rows, sheet_name="重抓效果报告")
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return False
        self.simple_progress_label.setText(f"已导出重抓效果报告：{file_path}")
        self.simple_status_label.setText("重抓效果报告已保存为 Excel")
        self.last_simple_retry_report_export_path = file_path
        self.last_simple_export_path = file_path
        self.refresh_simple_recent_area()
        self.simple_information("保存成功", f"已保存：\n{file_path}")
        return True

    def update_low_quality_retry_report(self, record):
        if not getattr(self, "low_quality_retry_active", False):
            return
        url = normalize_url(record.get("url", ""))
        baseline = getattr(self, "low_quality_retry_baseline", {}).get(url)
        if not baseline:
            return
        self.ensure_record_completeness(record)
        before_score = int(baseline.get("score") or 0)
        after_score = int(record.get("completeness_score") or 0)
        captured, still_missing = self.retry_report_captured_fields(
            baseline.get("missing", []),
            record.get("completeness_missing", []),
        )
        row = {
            "url": url,
            "title": record.get("title") or baseline.get("title") or "(无标题)",
            "before": before_score,
            "after": after_score,
            "delta": after_score - before_score,
            "captured": "、".join(captured) if captured else "暂无新增",
            "still_missing": "、".join(still_missing) if still_missing else "资料较完整",
            "captured_fields": captured,
            "still_missing_fields": still_missing,
        }
        rows = [item for item in getattr(self, "low_quality_retry_report_rows", []) if item.get("url") != url]
        rows.append(row)
        self.low_quality_retry_report_rows = rows
        self.refresh_low_quality_retry_report_summary()

    def set_collecting_buttons_state(self, running):
        running = bool(running)
        if hasattr(self, "start_button"):
            self.start_button.setEnabled(not running)
        if hasattr(self, "stop_button"):
            self.stop_button.setEnabled(running)
        if hasattr(self, "simple_start_button"):
            self.simple_start_button.setEnabled(not running)
            self.simple_start_button.setText("采集中" if running else "确认并采集")
        if hasattr(self, "simple_stop_button"):
            self.simple_stop_button.setEnabled(running)
            self.simple_stop_button.setText("正在停止" if running and getattr(self, "worker", None) and self.worker.should_stop() else "停止")
        if hasattr(self, "simple_retry_button"):
            self.simple_retry_button.setEnabled(not running)
        if hasattr(self, "simple_retry_low_quality_button"):
            self.simple_retry_low_quality_button.setEnabled(not running)
        for attr_name in (
            "simple_fix_pagination_button",
            "simple_fix_subpages_button",
            "simple_fix_login_button",
            "simple_fix_fields_button",
        ):
            button = getattr(self, attr_name, None)
            if button:
                button.setEnabled(not running)

    def build_simple_collect_tab(self):
        page = QWidget()
        page.setObjectName("simpleWorkbench")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        self.apply_simple_workbench_style(page)

        header_row = QHBoxLayout()
        title_stack = QVBoxLayout()
        title_label = QLabel("采集工作台")
        title_label.setObjectName("simplePageTitle")
        subtitle_label = QLabel("输入网址和目标资料，采集完成后在右侧检查详情并保存结果")
        subtitle_label.setObjectName("simplePageSubtitle")
        title_stack.addWidget(title_label)
        title_stack.addWidget(subtitle_label)
        self.simple_status_label = QLabel("准备就绪")
        self.simple_status_label.setObjectName("simpleStatusPill")
        self.simple_status_label.setWordWrap(True)
        header_row.addLayout(title_stack, 1)
        header_row.addWidget(self.simple_status_label)
        layout.addLayout(header_row)

        self.simple_input_box = QGroupBox("采集任务")
        input_box = self.simple_input_box
        input_box.setObjectName("primaryPanel")
        input_layout = QGridLayout(input_box)
        input_layout.setHorizontalSpacing(10)
        input_layout.setVerticalSpacing(8)
        self.simple_url_input = QTextEdit()
        self.simple_url_input.setMinimumHeight(82)
        self.simple_url_input.setMaximumHeight(110)
        self.simple_url_input.setPlaceholderText("粘贴网址，一行一个")
        self.simple_url_input.setPlainText("https://example.com/")
        self.simple_goal_input = QTextEdit()
        self.simple_goal_input.setMinimumHeight(72)
        self.simple_goal_input.setMaximumHeight(96)
        self.simple_goal_input.setPlaceholderText("告诉软件要抓什么，例如：抓产品名、价格、库存和详情页参数")
        self.simple_start_button = QPushButton("确认并采集")
        self.simple_start_button.setObjectName("primaryButton")
        self.simple_stop_button = QPushButton("停止")
        self.simple_stop_button.setEnabled(False)
        self.simple_ai_suggest_button = QPushButton("AI 建议列")
        self.simple_export_button = QPushButton("自动保存")
        self.simple_retry_report_button = QPushButton("导出重抓报告")
        self.simple_copy_button = QPushButton("复制表格")
        self.simple_contact_button = QPushButton("提取邮箱电话")
        self.simple_image_button = QPushButton("下载图片")
        self.simple_schedule_button = QPushButton("定时监控")
        self.simple_retry_button = QPushButton("重试失败")
        self.simple_retry_low_quality_button = QPushButton("重抓低完整度")
        self.simple_apply_diagnosis_button = QPushButton("应用诊断建议")
        self.simple_fix_pagination_button = QPushButton("重抓分页")
        self.simple_fix_subpages_button = QPushButton("重抓子链接")
        self.simple_fix_login_button = QPushButton("登录重试")
        self.simple_fix_fields_button = QPushButton("AI 修字段")
        self.simple_sample_verify_button = QPushButton("抽样验证")
        self.simple_strategy_compare_button = QPushButton("实测对比")
        self.simple_real_check_button = QPushButton("真实自检")
        self.simple_depth_combo = QComboBox()
        self.simple_depth_combo.addItem("普通", "normal")
        self.simple_depth_combo.addItem("深度", "deep")
        self.simple_depth_combo.addItem("完整", "complete")
        self.simple_depth_combo.setCurrentIndex(1)
        self.simple_depth_combo.currentIndexChanged.connect(self.on_simple_depth_changed)
        self.simple_start_button.clicked.connect(self.simple_prepare_and_start_collect)
        self.simple_stop_button.clicked.connect(self.stop_collecting)
        self.simple_ai_suggest_button.clicked.connect(self.simple_suggest_columns_now)
        self.simple_export_button.clicked.connect(self.simple_auto_save_results)
        self.simple_retry_report_button.clicked.connect(self.simple_export_retry_report)
        self.simple_copy_button.clicked.connect(self.copy_current_results_to_sheets)
        self.simple_contact_button.clicked.connect(self.simple_extract_contacts)
        self.simple_image_button.clicked.connect(self.simple_download_images)
        self.simple_schedule_button.clicked.connect(self.simple_add_schedule)
        self.simple_retry_button.clicked.connect(self.simple_retry_failed_items)
        self.simple_retry_low_quality_button.clicked.connect(self.simple_retry_low_quality_items)
        self.simple_apply_diagnosis_button.clicked.connect(self.simple_apply_diagnosis_action)
        self.simple_fix_pagination_button.clicked.connect(lambda: self.simple_apply_repair_plan_action("pagination"))
        self.simple_fix_subpages_button.clicked.connect(lambda: self.simple_apply_repair_plan_action("subpages"))
        self.simple_fix_login_button.clicked.connect(lambda: self.simple_apply_repair_plan_action("login"))
        self.simple_fix_fields_button.clicked.connect(lambda: self.simple_apply_repair_plan_action("fields"))
        self.simple_sample_verify_button.clicked.connect(self.simple_run_sample_verification)
        self.simple_strategy_compare_button.clicked.connect(self.simple_run_strategy_comparison)
        self.simple_real_check_button.clicked.connect(self.start_real_scrape_check)
        input_layout.addWidget(QLabel("网址"), 0, 0)
        input_layout.addWidget(self.simple_url_input, 0, 1, 1, 4)
        input_layout.addWidget(QLabel("要抓什么"), 1, 0)
        input_layout.addWidget(self.simple_goal_input, 1, 1, 1, 4)
        input_layout.addWidget(QLabel("采集深度"), 2, 0)
        input_layout.addWidget(self.simple_depth_combo, 2, 1)
        input_layout.addWidget(self.simple_start_button, 2, 2)
        input_layout.addWidget(self.simple_stop_button, 2, 3)
        input_layout.addWidget(self.simple_export_button, 2, 4)
        quick_actions = QHBoxLayout()
        quick_actions.addWidget(self.simple_copy_button)
        quick_actions.addWidget(self.simple_image_button)
        quick_actions.addWidget(self.simple_retry_report_button)
        quick_actions.addStretch(1)
        input_layout.addLayout(quick_actions, 3, 1, 1, 4)
        layout.addWidget(input_box)

        status_box = QGroupBox("采集状态")
        status_layout = QVBoxLayout(status_box)
        self.simple_step_labels = []
        step_row = QHBoxLayout()
        for text in ("1 输入", "2 后台采集", "3 导出"):
            label = QLabel(text)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setMinimumHeight(30)
            self.simple_step_labels.append(label)
            step_row.addWidget(label)
        status_layout.addLayout(step_row)
        self.set_simple_flow_step("输入")

        self.simple_progress_label = QLabel("流程：输入网址 -> 开始采集 -> 导出结果")
        self.simple_progress_label.setObjectName("simpleProgressText")
        self.simple_progress_label.setWordWrap(True)
        status_layout.addWidget(self.simple_progress_label)

        self.simple_result_summary_label = QLabel("结果：暂无")
        self.simple_result_summary_label.setObjectName("simpleSummaryText")
        self.simple_result_summary_label.setWordWrap(True)
        status_layout.addWidget(self.simple_result_summary_label)

        self.simple_retry_report_label = QLabel("重抓效果：暂无")
        self.simple_retry_report_label.setObjectName("simpleSummaryText")
        self.simple_retry_report_label.setWordWrap(True)
        status_layout.addWidget(self.simple_retry_report_label)

        self.simple_diagnosis_label = QLabel("诊断建议：等待结果")
        self.simple_diagnosis_label.setObjectName("simpleSummaryText")
        self.simple_diagnosis_label.setWordWrap(True)
        status_layout.addWidget(self.simple_diagnosis_label)

        self.simple_repair_plan_label = QLabel("修复方案：等待诊断")
        self.simple_repair_plan_label.setObjectName("simpleSummaryText")
        self.simple_repair_plan_label.setWordWrap(True)
        status_layout.addWidget(self.simple_repair_plan_label)
        repair_actions = QHBoxLayout()
        repair_actions.addWidget(self.simple_fix_pagination_button)
        repair_actions.addWidget(self.simple_fix_subpages_button)
        repair_actions.addWidget(self.simple_fix_login_button)
        repair_actions.addWidget(self.simple_fix_fields_button)
        repair_actions.addStretch(1)
        status_layout.addLayout(repair_actions)

        self.simple_sample_verify_label = QLabel("抽样验证：等待样本")
        self.simple_sample_verify_label.setObjectName("simpleSummaryText")
        self.simple_sample_verify_label.setWordWrap(True)
        status_layout.addWidget(self.simple_sample_verify_label)

        self.simple_strategy_compare_label = QLabel("实测对比：等待两种策略样本")
        self.simple_strategy_compare_label.setObjectName("simpleSummaryText")
        self.simple_strategy_compare_label.setWordWrap(True)
        status_layout.addWidget(self.simple_strategy_compare_label)

        self.simple_discovery_label = QLabel("发现记录：等待采集")
        self.simple_discovery_label.setObjectName("simpleSummaryText")
        self.simple_discovery_label.setWordWrap(True)
        status_layout.addWidget(self.simple_discovery_label)
        layout.addWidget(status_box)

        self.simple_ai_box = QGroupBox("AI 设置")
        ai_box = self.simple_ai_box
        ai_box.setCheckable(True)
        ai_box.setChecked(False)
        ai_layout = QGridLayout(ai_box)
        self.simple_ai_provider_combo = QComboBox()
        for provider, preset in AI_PROVIDER_PRESETS.items():
            self.simple_ai_provider_combo.addItem(preset.get("name", provider), provider)
        self.simple_ai_model_combo = QComboBox()
        self.simple_ai_key_input = QLineEdit()
        self.simple_ai_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.simple_ai_key_input.setPlaceholderText("API Key 保存在本机")
        self.simple_ai_save_button = QPushButton("保存")
        self.simple_ai_test_button = QPushButton("测试")
        self.simple_ai_provider_combo.currentIndexChanged.connect(self.on_simple_ai_provider_changed)
        self.simple_ai_save_button.clicked.connect(self.save_simple_ai_settings)
        self.simple_ai_test_button.clicked.connect(self.test_simple_ai_settings)
        ai_layout.addWidget(QLabel("厂商"), 0, 0)
        ai_layout.addWidget(self.simple_ai_provider_combo, 0, 1)
        ai_layout.addWidget(QLabel("模型"), 0, 2)
        ai_layout.addWidget(self.simple_ai_model_combo, 0, 3)
        ai_layout.addWidget(QLabel("Key"), 1, 0)
        ai_layout.addWidget(self.simple_ai_key_input, 1, 1, 1, 2)
        ai_layout.addWidget(self.simple_ai_save_button, 1, 3)
        ai_layout.addWidget(self.simple_ai_test_button, 1, 4)
        ai_tools_row = QHBoxLayout()
        ai_tools_row.addWidget(self.simple_ai_suggest_button)
        ai_tools_row.addWidget(self.simple_real_check_button)
        ai_tools_row.addStretch(1)
        ai_layout.addLayout(ai_tools_row, 2, 1, 1, 4)
        self.bind_collapsible_groupbox(ai_box, checked=False)
        self.load_simple_ai_settings_to_ui()

        self.simple_column_card_box = QGroupBox("准备抓取的列")
        self.simple_column_card_box.setCheckable(True)
        self.simple_column_card_box.setChecked(False)
        column_card_layout = QVBoxLayout(self.simple_column_card_box)
        self.simple_column_card_label = QLabel("标题｜正文｜图片｜链接")
        self.simple_column_card_label.setWordWrap(True)
        self.simple_column_table = QTableWidget(0, 2)
        self.simple_column_table.setHorizontalHeaderLabels(["启用", "列名"])
        self.simple_column_table.verticalHeader().setVisible(False)
        self.simple_column_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.simple_column_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.simple_column_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.simple_column_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.simple_column_delete_button = QPushButton("删除列")
        self.simple_column_delete_button.clicked.connect(self.delete_selected_simple_columns)
        self.simple_column_table.itemChanged.connect(self.on_simple_column_item_changed)
        column_card_layout.addWidget(self.simple_column_card_label)
        column_card_layout.addWidget(self.simple_column_table)
        column_card_layout.addWidget(self.simple_column_delete_button)
        self.bind_collapsible_groupbox(self.simple_column_card_box, checked=False)

        self.simple_result_table = self.create_simple_result_table()
        self.simple_result_table.itemSelectionChanged.connect(self.update_current_detail)
        self.simple_result_table.itemSelectionChanged.connect(self.update_simple_result_preview)
        result_box = QGroupBox("采集结果")
        result_layout = QVBoxLayout(result_box)
        result_layout.addWidget(self.simple_result_table)
        result_actions = QHBoxLayout()
        result_actions.addWidget(self.simple_contact_button)
        result_actions.addWidget(self.simple_schedule_button)
        result_actions.addWidget(self.simple_retry_button)
        result_actions.addWidget(self.simple_retry_low_quality_button)
        result_actions.addWidget(self.simple_apply_diagnosis_button)
        result_actions.addWidget(self.simple_sample_verify_button)
        result_actions.addWidget(self.simple_strategy_compare_button)
        result_actions.addStretch(1)
        result_layout.addLayout(result_actions)

        self.simple_field_table = QTableWidget(0, 0)
        self.simple_field_table.verticalHeader().setVisible(False)
        self.simple_field_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.simple_field_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        field_box = QGroupBox("按你的要求整理")
        field_layout = QVBoxLayout(field_box)
        self.simple_field_status_label = QLabel("字段：本地规则整理，暂无结果")
        self.simple_field_status_label.setWordWrap(True)
        field_layout.addWidget(self.simple_field_status_label)
        field_layout.addWidget(self.simple_field_table)

        preview_box = QGroupBox("结果预览")
        preview_layout = QGridLayout(preview_box)
        self.simple_preview_title_label = QLabel("未选择结果")
        self.simple_preview_title_label.setWordWrap(True)
        self.simple_preview_url_label = QLabel("")
        self.simple_preview_url_label.setWordWrap(True)
        self.simple_preview_counts_label = QLabel("图片 0｜链接 0｜表格 0")
        self.simple_preview_counts_label.setWordWrap(True)
        self.simple_preview_body_output = QTextEdit()
        self.simple_preview_body_output.setReadOnly(True)
        self.simple_preview_body_output.setMaximumHeight(96)
        preview_layout.addWidget(QLabel("标题"), 0, 0)
        preview_layout.addWidget(self.simple_preview_title_label, 0, 1)
        preview_layout.addWidget(QLabel("网址"), 1, 0)
        preview_layout.addWidget(self.simple_preview_url_label, 1, 1)
        preview_layout.addWidget(QLabel("资料"), 2, 0)
        preview_layout.addWidget(self.simple_preview_counts_label, 2, 1)
        preview_layout.addWidget(QLabel("正文"), 3, 0)
        preview_layout.addWidget(self.simple_preview_body_output, 3, 1)

        self.simple_recent_box = QGroupBox("最近结果")
        recent_box = self.simple_recent_box
        recent_box.setCheckable(True)
        recent_box.setChecked(False)
        recent_layout = QVBoxLayout(recent_box)
        self.simple_recent_files_table = QTableWidget(0, 3)
        self.simple_recent_files_table.setHorizontalHeaderLabels(["文件", "时间", "位置"])
        self.simple_recent_files_table.verticalHeader().setVisible(False)
        self.simple_recent_files_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.simple_recent_files_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.simple_recent_files_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.simple_recent_files_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.simple_recent_files_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.simple_recent_files_table.itemDoubleClicked.connect(self.open_selected_simple_recent_file)
        self.simple_open_recent_file_button = QPushButton("打开文件")
        self.simple_open_recent_folder_button = QPushButton("打开文件夹")
        self.simple_open_recent_file_button.clicked.connect(self.open_selected_simple_recent_file)
        self.simple_open_recent_folder_button.clicked.connect(self.open_simple_recent_export_folder)
        self.simple_recent_records_table = QTableWidget(0, 3)
        self.simple_recent_records_table.setHorizontalHeaderLabels(["标题", "网址", "时间"])
        self.simple_recent_records_table.verticalHeader().setVisible(False)
        self.simple_recent_records_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.simple_recent_records_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.simple_recent_records_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.simple_recent_records_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.simple_recent_records_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        recent_files_header = QHBoxLayout()
        recent_files_header.addWidget(QLabel("最近保存的 Excel"), 1)
        recent_files_header.addWidget(self.simple_open_recent_file_button)
        recent_files_header.addWidget(self.simple_open_recent_folder_button)
        recent_layout.addLayout(recent_files_header)
        recent_layout.addWidget(self.simple_recent_files_table)
        recent_layout.addWidget(QLabel("最近采集记录"))
        recent_layout.addWidget(self.simple_recent_records_table)
        self.bind_collapsible_groupbox(recent_box, checked=False)

        left_splitter = QSplitter(Qt.Orientation.Vertical)
        left_splitter.addWidget(result_box)
        left_splitter.addWidget(field_box)
        left_splitter.setSizes([420, 240])

        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.addWidget(preview_box)
        right_splitter.addWidget(self.simple_column_card_box)
        right_splitter.addWidget(ai_box)
        right_splitter.addWidget(recent_box)
        right_splitter.setSizes([240, 80, 70, 80])

        self.simple_main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.simple_main_splitter.addWidget(left_splitter)
        self.simple_main_splitter.addWidget(right_splitter)
        self.simple_main_splitter.setSizes([850, 360])
        layout.addWidget(self.simple_main_splitter, 1)

        self.refresh_simple_recent_area()
        self.on_simple_depth_changed()
        return page

    def apply_simple_workbench_style(self, page):
        page.setStyleSheet(
            """
            QWidget#simpleWorkbench {
                background: #f6f8fa;
                color: #1f2937;
                font-size: 13px;
            }
            QLabel#simplePageTitle {
                font-size: 20px;
                font-weight: 700;
                color: #111827;
            }
            QLabel#simplePageSubtitle {
                color: #6b7280;
            }
            QLabel#simpleStatusPill {
                background: #eef2ff;
                color: #3730a3;
                border: 1px solid #c7d2fe;
                border-radius: 6px;
                padding: 6px 10px;
            }
            QLabel#simpleProgressText, QLabel#simpleSummaryText {
                color: #374151;
            }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #dbe3ef;
                border-radius: 6px;
                margin-top: 10px;
                padding: 10px;
                font-weight: 600;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                color: #111827;
            }
            QTextEdit, QLineEdit, QComboBox, QTableWidget {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 4px;
                font-weight: 400;
            }
            QPushButton {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 6px 10px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #f1f5f9;
            }
            QPushButton#primaryButton {
                background: #2563eb;
                border: 1px solid #1d4ed8;
                color: #ffffff;
            }
            QPushButton#primaryButton:hover {
                background: #1d4ed8;
            }
            QHeaderView::section {
                background: #f8fafc;
                border: 0;
                border-bottom: 1px solid #e5e7eb;
                padding: 5px;
                font-weight: 600;
            }
            """
        )

    def bind_collapsible_groupbox(self, group_box, checked=False):
        group_box.setChecked(bool(checked))
        expanded_min_height = group_box.minimumHeight()

        def set_children_visible(visible):
            layout = group_box.layout()
            if not layout:
                return
            for index in range(layout.count()):
                item = layout.itemAt(index)
                widget = item.widget()
                if widget:
                    widget.setVisible(bool(visible))
                child_layout = item.layout()
                if child_layout:
                    for child_index in range(child_layout.count()):
                        child_item = child_layout.itemAt(child_index)
                        child_widget = child_item.widget()
                        if child_widget:
                            child_widget.setVisible(bool(visible))
            if visible:
                group_box.setMaximumHeight(16777215)
                group_box.setMinimumHeight(expanded_min_height)
            else:
                group_box.setMinimumHeight(26)
                group_box.setMaximumHeight(34)

        group_box.toggled.connect(set_children_visible)
        set_children_visible(checked)

    def simple_collect_depth_config(self, mode=None):
        if mode is None and hasattr(self, "simple_depth_combo"):
            mode = self.simple_depth_combo.currentData() or "deep"
        mode = mode or "deep"
        configs = {
            "normal": {
                "label": "普通",
                "subpage_limit": 3,
                "page_limit": 1,
                "scroll_times": 1,
                "progress": "后台：快速读取网页，并补充最多 3 个同站详情页",
            },
            "deep": {
                "label": "深度",
                "subpage_limit": 12,
                "page_limit": 3,
                "scroll_times": 3,
                "progress": "后台：深度读取网页、自动翻页，并补充最多 12 个同站详情页",
            },
            "complete": {
                "label": "完整",
                "subpage_limit": 30,
                "page_limit": 5,
                "scroll_times": 5,
                "progress": "后台：尽量完整读取网页、自动翻页和更多同站详情页",
            },
        }
        return configs.get(mode, configs["deep"])

    def apply_simple_depth_mode(self, mode):
        if hasattr(self, "simple_depth_combo"):
            index = self.simple_depth_combo.findData(mode)
            if index >= 0:
                self.simple_depth_combo.setCurrentIndex(index)
        return self.simple_collect_depth_config(mode)

    def on_simple_depth_changed(self):
        if not hasattr(self, "simple_progress_label") or self.worker:
            return
        config = self.simple_collect_depth_config()
        self.simple_progress_label.setText(config["progress"])

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

    def simple_input_lines(self):
        if not hasattr(self, "simple_url_input"):
            return []
        lines = []
        for line in self.simple_url_input.toPlainText().splitlines():
            value = line.strip().strip('"')
            if value:
                lines.append(value)
        return lines

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

    def simple_prepare_file_extract(self, file_path):
        instruction = self.simple_goal_input.toPlainText().strip() if hasattr(self, "simple_goal_input") else ""
        if hasattr(self, "simple_status_label"):
            self.simple_status_label.setText("识别为本地文件，后台用 AI 转成表格")
        if hasattr(self, "simple_progress_label"):
            self.simple_progress_label.setText(f"后台：正在处理文件 {os.path.basename(file_path)}")
        self.set_simple_flow_step("采集")
        self.set_expert_mode(False)
        self.run_ai_worker("extract_file", {"file_path": file_path, "instruction": instruction})
        return True

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

    def simple_base_field_rules(self):
        if getattr(self, "simple_ai_field_rules", []):
            return list(self.simple_ai_field_rules)
        return [FieldRule(name, "") for name in self.simple_requested_field_names()]

    def simple_visible_column_rules(self):
        hidden = set(getattr(self, "simple_column_hidden", set()) or set())
        return [
            rule for rule in self.simple_base_field_rules()
            if getattr(rule, "name", "") and getattr(rule, "name", "") not in hidden
        ]

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

    def simple_select_default_template(self):
        if not hasattr(self, "template_combo"):
            return
        index = self.template_combo.findText("通用自动识别")
        if index >= 0:
            self.template_combo.setCurrentIndex(index)

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

    def set_simple_flow_step(self, active_step):
        labels = getattr(self, "simple_step_labels", [])
        steps = [("输入", "1 输入"), ("采集", "2 后台采集"), ("导出", "3 导出")]
        for index, (key, text) in enumerate(steps):
            if index >= len(labels):
                continue
            label = labels[index]
            if key == active_step:
                label.setText(f"{text}：进行中")
                label.setStyleSheet("background:#e6f4ff;color:#0958d9;border:1px solid #91caff;border-radius:4px;padding:4px;")
            elif (active_step == "采集" and key == "输入") or (active_step == "导出" and key in {"输入", "采集"}):
                label.setText(f"{text}：完成")
                label.setStyleSheet("background:#f6ffed;color:#237804;border:1px solid #b7eb8f;border-radius:4px;padding:4px;")
            else:
                label.setText(f"{text}：待办")
                label.setStyleSheet("background:#f5f5f5;color:#595959;border:1px solid #d9d9d9;border-radius:4px;padding:4px;")

    def simple_result_summary_text(self):
        if not getattr(self, "records", []):
            return "结果：暂无"
        counts = {"新增": 0, "变化": 0, "重复": 0, "错误": 0}
        scores = []
        for record in self.records:
            self.ensure_record_completeness(record)
            status = self.record_status_text(record)
            counts[status] = counts.get(status, 0) + 1
            scores.append(int(record.get("completeness_score") or 0))
        parts = [f"{name} {count}" for name, count in counts.items() if count]
        average = int(sum(scores) / len(scores)) if scores else 0
        return f"结果：共 {len(self.records)} 条，平均完整度 {average}%，" + "，".join(parts)

    def record_links_matching_tokens(self, record, tokens):
        matched = []
        for link in record.get("links", []) or []:
            if isinstance(link, dict):
                text = str(link.get("text") or link.get("title") or "")
                url = str(link.get("url") or link.get("href") or "")
            else:
                text = str(link)
                url = str(link)
            combined = f"{text} {url}".lower()
            if any(token in combined for token in tokens):
                matched.append({"text": text, "url": url})
        return matched

    def pagination_like_links(self, record):
        tokens = (
            "下一页",
            "下页",
            "翻页",
            "页码",
            "加载更多",
            "pagination",
            "pager",
            "next",
            "page=",
            "/page",
            "page/",
        )
        return self.record_links_matching_tokens(record, tokens)

    def detail_like_links(self, record):
        tokens = (
            "详情",
            "商品",
            "宝贝",
            "查看",
            "detail",
            "item",
            "product",
            "goods",
            "offer",
            "/p/",
            "/item/",
            "/detail",
            "/product",
        )
        return self.record_links_matching_tokens(record, tokens)

    def crawl_diagnosis_for_record(self, record):
        self.ensure_record_completeness(record)
        missing = set(record.get("completeness_missing", []) or [])
        score = int(record.get("completeness_score") or 0)
        body_text = compact_text(record.get("body", ""), 2000)
        error_text = compact_text(record.get("error", ""), 500)
        link_count = len(record.get("links", []) or [])
        image_count = len(record.get("images", []) or [])
        table_count = len(record.get("tables", []) or [])
        pagination_links = self.pagination_like_links(record)
        detail_links = self.detail_like_links(record)
        if error_text:
            lower_error = error_text.lower()
            if any(token in lower_error for token in ("403", "401", "captcha", "验证码", "登录", "forbidden", "access denied")):
                return {
                    "reason": "反爬或权限限制",
                    "advice": "改用真实浏览器、保持登录，并加大延迟后重试。",
                    "severity": "需处理",
                }
            return {
                "reason": "请求失败",
                "advice": "查看错误列，降低速度或稍后重试。",
                "severity": "需处理",
            }
        if score >= 85:
            return {"reason": "资料较完整", "advice": "可以直接导出或加入监控。", "severity": "正常"}
        if pagination_links and ("正文" in missing or score < 70):
            return {
                "reason": "分页可能未继续",
                "advice": "应用诊断建议会切到完整模式，提高翻页、滚动和等待，继续读取下一页/更多内容。",
                "severity": "需处理",
                "pagination_links": len(pagination_links),
                "detail_links": len(detail_links),
            }
        if detail_links and missing.intersection({"图片", "价格", "表格/规格", "正文"}):
            return {
                "reason": "子链接未展开",
                "advice": "使用“重抓低完整度”让完整模式自动进入同站详情/商品子链接，补图片、价格和规格。",
                "severity": "需处理",
                "pagination_links": len(pagination_links),
                "detail_links": len(detail_links),
            }
        if len(body_text) < 40 and image_count == 0 and table_count == 0:
            return {
                "reason": "疑似动态加载",
                "advice": "使用完整模式重抓，增加滚动次数和等待时间。",
                "severity": "需处理",
            }
        if missing.intersection({"图片", "价格", "表格/规格"}) and link_count:
            return {
                "reason": "详情页可能未展开",
                "advice": "使用“重抓低完整度”让完整模式补详情页、图片和规格。",
                "severity": "需处理",
            }
        if body_text and len(missing) >= 3:
            return {
                "reason": "字段规则可能不匹配",
                "advice": "点击 AI 建议列或到 AI 抓取工作台修复字段规则。",
                "severity": "需确认",
            }
        if "链接" in missing and missing.intersection({"图片", "价格", "表格/规格"}):
            return {
                "reason": "子链接候选不足",
                "advice": "应用诊断建议会切到完整模式；若仍抓不到，请到 AI 工作台扫描并手动选择子页面链接。",
                "severity": "需确认",
                "pagination_links": len(pagination_links),
                "detail_links": len(detail_links),
            }
        return {
            "reason": "页面资料偏少",
            "advice": "抽查原网页；若网页本身信息少，可接受低完整度或减少字段要求。",
            "severity": "需确认",
        }

    def simple_crawl_diagnosis_rows(self, records=None):
        rows = []
        for record in list(records if records is not None else getattr(self, "records", [])):
            if not isinstance(record, dict):
                continue
            diagnosis = self.crawl_diagnosis_for_record(record)
            rows.append(
                {
                    "url": normalize_url(record.get("url", "")),
                    "title": record.get("title") or "(无标题)",
                    "score": int(record.get("completeness_score") or 0),
                    "missing": "、".join(record.get("completeness_missing", []) or []),
                    **diagnosis,
                }
            )
        return rows

    def simple_crawl_diagnosis_text(self):
        rows = self.simple_crawl_diagnosis_rows()
        if not rows:
            return "诊断建议：等待结果"
        weak_rows = [row for row in rows if int(row.get("score") or 0) < 60 or row.get("severity") != "正常"]
        if not weak_rows:
            return f"诊断建议：{len(rows)} 条资料较完整，可以导出或加入监控"
        reason_counts = {}
        reason_severity = {}
        severity_rank = {"需处理": 2, "需确认": 1, "正常": 0}
        for row in weak_rows:
            reason = row.get("reason", "页面资料偏少")
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            reason_severity[reason] = max(
                reason_severity.get(reason, 0),
                severity_rank.get(row.get("severity", "需确认"), 1),
            )
        top_reason, top_count = sorted(
            reason_counts.items(),
            key=lambda item: (reason_severity.get(item[0], 0), item[1]),
            reverse=True,
        )[0]
        top_row = next((row for row in weak_rows if row.get("reason") == top_reason), weak_rows[0])
        return f"诊断建议：{len(weak_rows)} 条需处理；主要是{top_reason} {top_count} 条。建议：{top_row.get('advice', '')}"

    def simple_repair_plan_groups(self, records=None):
        categories = {
            "pagination": {
                "label": "分页",
                "button": "重抓分页",
                "reasons": {"分页可能未继续"},
                "urls": [],
            },
            "subpages": {
                "label": "子链接",
                "button": "重抓子链接",
                "reasons": {"子链接未展开", "详情页可能未展开", "子链接候选不足", "疑似动态加载"},
                "urls": [],
            },
            "login": {
                "label": "登录/请求",
                "button": "登录重试",
                "reasons": {"反爬或权限限制", "请求失败"},
                "urls": [],
            },
            "fields": {
                "label": "字段",
                "button": "AI 修字段",
                "reasons": {"字段规则可能不匹配"},
                "urls": [],
            },
        }
        for row in self.simple_crawl_diagnosis_rows(records):
            if row.get("severity") == "正常":
                continue
            url = normalize_url(row.get("url", ""))
            reason = row.get("reason", "")
            if not url:
                continue
            for group in categories.values():
                if reason in group["reasons"] and url not in group["urls"]:
                    group["urls"].append(url)
        return categories

    def simple_repair_plan_text(self):
        groups = self.simple_repair_plan_groups()
        active = [group for group in groups.values() if group.get("urls")]
        if not active:
            return "修复方案：等待诊断，或当前结果不需要自动修复"
        parts = [f"{group['label']} {len(group['urls'])} 条 -> {group['button']}" for group in active]
        return "修复方案：" + "；".join(parts)

    def start_complete_retry_for_urls(self, urls, status_text, progress_text):
        urls = [normalize_url(url) for url in urls or []]
        urls = [url for index, url in enumerate(urls) if url and url not in urls[:index]]
        if not urls:
            self.simple_information("提示", "当前没有可重抓的网址。")
            return False
        if self.worker:
            self.simple_status_label.setText("正在采集，请先等待当前任务结束")
            self.simple_information("提示", "正在采集，请先等待当前任务结束。")
            return False
        depth_config = self.apply_complete_crawl_settings()
        self.simple_select_default_template()
        self.simple_merge_subpage_results = True
        self.simple_subpage_parent_map = {}
        self.simple_url_input.setPlainText("\n".join(urls))
        self.sync_simple_inputs_to_background()
        self.simple_status_label.setText(status_text)
        self.simple_progress_label.setText(progress_text)
        self.append_log(f"{status_text}：{len(urls)} 个网址。")
        self.start_collecting(
            skip_confirmation=True,
            runtime_overrides={
                "scrape_subpages": True,
                "subpage_limit": depth_config["subpage_limit"],
                "selected_subpage_urls": [],
                "simple_auto_subpages": True,
                "simple_collect_depth": depth_config["label"],
                "skip_unchanged": False,
            },
        )
        return True

    def simple_apply_repair_plan_action(self, category):
        groups = self.simple_repair_plan_groups()
        group = groups.get(category, {})
        urls = group.get("urls", [])
        if not urls:
            self.simple_status_label.setText(f"修复方案：当前没有需要{group.get('button', '处理')}的网址")
            return False
        if category == "fields":
            if self.maybe_start_simple_ai_suggest_fields(urls):
                self.simple_status_label.setText(f"修复方案：AI 正在为 {len(urls)} 条结果整理字段")
            else:
                self.simple_status_label.setText("修复方案：请检查 AI 设置后再修字段")
            return True
        if category == "login":
            self.apply_blocked_crawl_settings()
            self.simple_url_input.setPlainText("\n".join(urls))
            self.sync_simple_inputs_to_background()
            self.simple_status_label.setText(f"修复方案：已启用真实浏览器和保留登录，准备重试 {len(urls)} 条")
            self.simple_progress_label.setText("下一次采集会保留登录状态，并用更慢速度访问")
            return True
        if category == "pagination":
            return self.start_complete_retry_for_urls(
                urls,
                f"正在完整模式重抓 {len(urls)} 条分页不足结果",
                "后台：提高翻页、滚动和等待，继续读取下一页/更多内容",
            )
        if category == "subpages":
            return self.start_complete_retry_for_urls(
                urls,
                f"正在完整模式重抓 {len(urls)} 条子链接不足结果",
                "后台：自动进入同站详情/商品子链接，补图片、价格、规格和正文",
            )
        return False

    def primary_simple_crawl_diagnosis(self):
        rows = self.simple_crawl_diagnosis_rows()
        weak_rows = [row for row in rows if int(row.get("score") or 0) < 60 or row.get("severity") != "正常"]
        if not weak_rows:
            return {}
        severity_rank = {"需处理": 2, "需确认": 1, "正常": 0}
        weak_rows.sort(
            key=lambda row: (
                severity_rank.get(row.get("severity", "需确认"), 1),
                100 - int(row.get("score") or 0),
            ),
            reverse=True,
        )
        return weak_rows[0]

    def apply_complete_crawl_settings(self):
        complete_index = self.simple_depth_combo.findData("complete") if hasattr(self, "simple_depth_combo") else -1
        if complete_index >= 0:
            self.simple_depth_combo.setCurrentIndex(complete_index)
        depth_config = self.simple_collect_depth_config()
        self.use_browser_checkbox.setChecked(True)
        self.page_limit_input.setValue(max(self.page_limit_input.value(), depth_config["page_limit"]))
        self.scroll_times_input.setValue(max(self.scroll_times_input.value(), depth_config["scroll_times"]))
        self.delay_input.setValue(max(self.delay_input.value(), 2))
        return depth_config

    def apply_blocked_crawl_settings(self):
        self.use_browser_checkbox.setChecked(True)
        self.keep_login_checkbox.setChecked(True)
        self.delay_input.setValue(max(self.delay_input.value(), 3))
        self.scroll_times_input.setValue(max(self.scroll_times_input.value(), 2))

    def simple_apply_diagnosis_action(self):
        diagnosis = self.primary_simple_crawl_diagnosis()
        if not diagnosis:
            self.simple_information("提示", "当前没有需要处理的诊断建议。")
            return False
        reason = diagnosis.get("reason", "")
        if reason in {"疑似动态加载", "详情页可能未展开", "分页可能未继续", "子链接未展开", "子链接候选不足"}:
            self.apply_complete_crawl_settings()
            if self.low_quality_urls():
                self.simple_status_label.setText("已应用诊断建议：完整模式重抓低完整度结果")
                return self.simple_retry_low_quality_items()
            self.simple_status_label.setText("已应用诊断建议：切换到完整模式并提高滚动/等待")
            self.simple_progress_label.setText("下一次采集会使用真实浏览器、完整深度和更长等待")
            return True
        if reason == "反爬或权限限制":
            self.apply_blocked_crawl_settings()
            self.simple_status_label.setText("已应用诊断建议：真实浏览器、保留登录、降低速度")
            self.simple_progress_label.setText("下一次采集会保留登录状态，并用更慢速度访问")
            return True
        if reason == "请求失败":
            self.use_browser_checkbox.setChecked(True)
            self.delay_input.setValue(max(self.delay_input.value(), 3))
            self.simple_status_label.setText("已应用诊断建议：启用真实浏览器并降低速度")
            self.simple_progress_label.setText("下一次采集会用更稳的访问方式重试")
            return True
        if reason == "字段规则可能不匹配":
            urls = [diagnosis.get("url", "")] if diagnosis.get("url", "") else self.urls_from_input()
            urls = [url for url in urls if url]
            if urls and self.maybe_start_simple_ai_suggest_fields(urls):
                self.simple_status_label.setText("已应用诊断建议：AI 正在整理字段规则")
            else:
                self.simple_status_label.setText("已应用诊断建议：请检查 AI 设置后再生成建议列")
            return True
        self.simple_status_label.setText("诊断建议：页面资料可能本身偏少，建议抽查原网页")
        return True

    def sample_verification_strategy_scores(self, rows):
        scores = {
            "普通": 55,
            "深度": 70,
            "完整": 75,
            "登录浏览器": 65,
            "AI字段修复": 60,
        }
        for row in rows or []:
            reason = row.get("reason", "")
            score = int(row.get("score") or 0)
            if reason == "资料较完整":
                scores["普通"] += 8
                scores["深度"] += 5
            elif reason == "疑似动态加载":
                scores["完整"] += 20
                scores["登录浏览器"] += 12
                scores["普通"] -= 15
            elif reason in {"详情页可能未展开", "子链接未展开"}:
                scores["深度"] += 12
                scores["完整"] += 18
                scores["普通"] -= 10
            elif reason == "分页可能未继续":
                scores["完整"] += 20
                scores["深度"] += 12
                scores["普通"] -= 12
            elif reason == "子链接候选不足":
                scores["完整"] += 10
                scores["AI字段修复"] += 8
            elif reason == "反爬或权限限制":
                scores["登录浏览器"] += 25
                scores["普通"] -= 20
                scores["深度"] -= 8
            elif reason == "字段规则可能不匹配":
                scores["AI字段修复"] += 22
                scores["完整"] += 4
            elif reason == "请求失败":
                scores["登录浏览器"] += 16
                scores["普通"] -= 12
            elif score < 60:
                scores["完整"] += 8
        return {name: max(0, min(100, value)) for name, value in scores.items()}

    def build_sample_verification_report(self, records=None):
        rows = self.simple_crawl_diagnosis_rows(records)
        if not rows:
            urls = self.urls_from_input()[:5]
            if not urls:
                return {
                    "summary": "抽样验证：请先输入或采集 3-5 个网址",
                    "recommendation": "",
                    "scores": {},
                    "rows": [],
                }
            rows = [
                {
                    "url": url,
                    "title": "(待采样)",
                    "score": 0,
                    "missing": "",
                    "reason": "等待样本",
                    "advice": "先用深度模式采集样本，再运行抽样验证。",
                    "severity": "需确认",
                }
                for url in urls
            ]
        sample_rows = rows[:5]
        scores = self.sample_verification_strategy_scores(sample_rows)
        recommendation = max(scores.items(), key=lambda item: item[1])[0] if scores else ""
        reason_counts = {}
        for row in sample_rows:
            reason = row.get("reason", "页面资料偏少")
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        reason_text = "、".join(f"{reason} {count}" for reason, count in sorted(reason_counts.items(), key=lambda item: item[1], reverse=True)[:3])
        summary = f"抽样验证：样本 {len(sample_rows)} 条，推荐 {recommendation}；主要原因：{reason_text}"
        return {
            "summary": summary,
            "recommendation": recommendation,
            "scores": scores,
            "rows": sample_rows,
        }

    def simple_run_sample_verification(self):
        report = self.build_sample_verification_report()
        self.latest_sample_verification_report = report
        summary = report.get("summary", "抽样验证：等待样本")
        if hasattr(self, "simple_sample_verify_label"):
            self.simple_sample_verify_label.setText(summary)
        recommendation = report.get("recommendation", "")
        if recommendation == "完整":
            self.apply_complete_crawl_settings()
        elif recommendation == "登录浏览器":
            self.apply_blocked_crawl_settings()
        elif recommendation == "深度":
            deep_index = self.simple_depth_combo.findData("deep") if hasattr(self, "simple_depth_combo") else -1
            if deep_index >= 0:
                self.simple_depth_combo.setCurrentIndex(deep_index)
        elif recommendation == "AI字段修复":
            self.simple_status_label.setText("抽样验证建议：优先使用 AI 建议列修复字段")
        if hasattr(self, "simple_progress_label"):
            score_text = "，".join(f"{name}{score}" for name, score in report.get("scores", {}).items())
            self.simple_progress_label.setText(f"{summary}。策略评分：{score_text}")
        return bool(report.get("rows"))

    def record_strategy_label(self, record):
        label = record.get("simple_collect_depth") or record.get("crawl_strategy") or record.get("strategy") or ""
        if label:
            return str(label)
        run_id = int(record.get("run_id") or 0)
        if run_id:
            config = self.database.run_config(run_id)
            label = (config or {}).get("simple_collect_depth") or ""
            if label:
                return str(label)
        return ""

    def strategy_comparison_rows(self, records=None):
        grouped = {}
        for record in list(records if records is not None else getattr(self, "records", [])):
            if not isinstance(record, dict):
                continue
            label = self.record_strategy_label(record)
            if not label:
                continue
            self.ensure_record_completeness(record)
            bucket = grouped.setdefault(
                label,
                {
                    "strategy": label,
                    "count": 0,
                    "scores": [],
                    "images": 0,
                    "links": 0,
                    "tables": 0,
                    "errors": 0,
                    "urls": set(),
                },
            )
            bucket["count"] += 1
            bucket["scores"].append(int(record.get("completeness_score") or 0))
            bucket["images"] += len(record.get("images", []) or [])
            bucket["links"] += len(record.get("links", []) or [])
            bucket["tables"] += len(record.get("tables", []) or [])
            bucket["errors"] += 1 if record.get("error") else 0
            if record.get("url"):
                bucket["urls"].add(record.get("url"))
        rows = []
        for bucket in grouped.values():
            count = max(1, int(bucket.get("count") or 0))
            avg_score = round(sum(bucket.get("scores") or []) / count)
            rows.append(
                {
                    "strategy": bucket.get("strategy", ""),
                    "count": bucket.get("count", 0),
                    "avg_score": avg_score,
                    "images": bucket.get("images", 0),
                    "links": bucket.get("links", 0),
                    "tables": bucket.get("tables", 0),
                    "errors": bucket.get("errors", 0),
                    "url_count": len(bucket.get("urls", set())),
                    "value_score": avg_score
                    + min(15, int(bucket.get("images", 0)))
                    + min(15, int(bucket.get("links", 0)) // 2)
                    + min(15, int(bucket.get("tables", 0)) * 2)
                    - int(bucket.get("errors", 0)) * 10,
                }
            )
        rows.sort(key=lambda row: (-int(row.get("value_score", 0)), row.get("strategy", "")))
        return rows

    def build_strategy_comparison_report(self, records=None):
        rows = self.strategy_comparison_rows(records)
        if len(rows) < 2:
            return {
                "summary": "实测对比：需要至少两种策略样本，例如先普通抓一次，再完整抓一次",
                "best": "",
                "delta": 0,
                "rows": rows,
            }
        best = rows[0]
        baseline = next((row for row in rows if row.get("strategy") == "普通"), rows[-1])
        delta = int(best.get("avg_score") or 0) - int(baseline.get("avg_score") or 0)
        more_links = int(best.get("links") or 0) - int(baseline.get("links") or 0)
        more_images = int(best.get("images") or 0) - int(baseline.get("images") or 0)
        more_tables = int(best.get("tables") or 0) - int(baseline.get("tables") or 0)
        summary = (
            f"实测对比：推荐 {best.get('strategy')}；完整度 {delta:+d} 分，"
            f"链接 {more_links:+d}，图片 {more_images:+d}，表格 {more_tables:+d}"
        )
        return {
            "summary": summary,
            "best": best.get("strategy", ""),
            "delta": delta,
            "rows": rows,
        }

    def strategy_dual_run_overrides(self, mode):
        depth_config = self.simple_collect_depth_config(mode)
        return {
            "scrape_subpages": True,
            "subpage_limit": depth_config["subpage_limit"],
            "selected_subpage_urls": [],
            "simple_auto_subpages": True,
            "simple_collect_depth": depth_config["label"],
            "skip_unchanged": False,
        }

    def prepare_strategy_dual_run_mode(self, mode):
        depth_config = self.apply_simple_depth_mode(mode)
        self.use_browser_checkbox.setChecked(True)
        self.page_limit_input.setValue(depth_config["page_limit"])
        self.scroll_times_input.setValue(max(depth_config["scroll_times"], self.scroll_times_input.value()))
        self.delay_input.setValue(max(1, self.delay_input.value()))
        self.keep_login_checkbox.setChecked(False)
        self.subpage_checkbox.setChecked(False)
        self.subpage_limit_input.setValue(0)
        self.selected_subpage_urls = []
        return depth_config

    def start_strategy_dual_run(self):
        if self.worker:
            if hasattr(self, "simple_strategy_compare_label"):
                self.simple_strategy_compare_label.setText("实测对比：当前采集运行中，完成后再开始对比")
            return False
        self.sync_simple_inputs_to_background()
        urls = self.urls_from_input()
        if not urls:
            self.simple_information("提示", "请先输入至少一个网址，再运行实测对比。")
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
        self.simple_select_default_template()
        depth_config = self.prepare_strategy_dual_run_mode("normal")
        self.strategy_dual_run_active = True
        self.strategy_dual_run_ready_report = False
        self.strategy_dual_run_step = "普通"
        self.strategy_dual_run_urls = list(urls)
        self.strategy_dual_run_records_before = len(self.records)
        if hasattr(self, "simple_strategy_compare_label"):
            self.simple_strategy_compare_label.setText("实测对比：正在采集普通模式样本")
        if hasattr(self, "simple_status_label"):
            self.simple_status_label.setText("实测对比：先用普通模式采集样本")
        if hasattr(self, "simple_progress_label"):
            self.simple_progress_label.setText(depth_config["progress"])
        self.set_simple_flow_step("采集")
        self.append_log("实测对比已启动：先运行普通模式，再自动运行完整模式。")
        self.start_collecting(
            skip_confirmation=True,
            runtime_overrides=self.strategy_dual_run_overrides("normal"),
        )
        return True

    def maybe_continue_strategy_dual_run(self, status):
        if not getattr(self, "strategy_dual_run_active", False):
            return False
        if status not in ("finished", "partial"):
            self.strategy_dual_run_active = False
            self.strategy_dual_run_step = ""
            self.strategy_dual_run_urls = []
            if hasattr(self, "simple_strategy_compare_label"):
                self.simple_strategy_compare_label.setText(f"实测对比：采集结束为 {status}，未继续自动对比")
            return False
        if self.strategy_dual_run_step == "普通":
            self.strategy_dual_run_step = "完整"
            urls = list(self.strategy_dual_run_urls or self.urls_from_input())
            if urls:
                self.url_input.setPlainText("\n".join(urls))
            depth_config = self.prepare_strategy_dual_run_mode("complete")
            if hasattr(self, "simple_strategy_compare_label"):
                self.simple_strategy_compare_label.setText("实测对比：普通样本完成，正在采集完整模式样本")
            if hasattr(self, "simple_status_label"):
                self.simple_status_label.setText("实测对比：继续用完整模式采集样本")
            if hasattr(self, "simple_progress_label"):
                self.simple_progress_label.setText(depth_config["progress"])
            self.append_log("实测对比：普通模式完成，开始完整模式。")
            self.start_collecting(
                skip_confirmation=True,
                runtime_overrides=self.strategy_dual_run_overrides("complete"),
            )
            return True
        if self.strategy_dual_run_step == "完整":
            self.strategy_dual_run_active = False
            self.strategy_dual_run_step = ""
            self.strategy_dual_run_urls = []
            self.strategy_dual_run_ready_report = True
        return False

    def finalize_strategy_dual_run_report(self):
        if not getattr(self, "strategy_dual_run_ready_report", False):
            return False
        self.strategy_dual_run_ready_report = False
        records = getattr(self, "records", [])[int(self.strategy_dual_run_records_before or 0):]
        report = self.build_strategy_comparison_report(records)
        if len(report.get("rows", [])) < 2:
            report = self.build_strategy_comparison_report()
        self.latest_strategy_comparison_report = report
        summary = report.get("summary", "实测对比：等待两种策略样本")
        if hasattr(self, "simple_strategy_compare_label"):
            self.simple_strategy_compare_label.setText(summary)
        if hasattr(self, "simple_status_label"):
            self.simple_status_label.setText(summary)
        if hasattr(self, "simple_progress_label"):
            rows_text = "；".join(
                f"{row.get('strategy')} 完整度{row.get('avg_score')} 链接{row.get('links')}"
                for row in report.get("rows", [])[:3]
            )
            self.simple_progress_label.setText(f"{summary}。{rows_text}")
        best = report.get("best", "")
        if best == "完整":
            self.apply_complete_crawl_settings()
        elif best == "深度":
            self.apply_simple_depth_mode("deep")
        elif best == "普通":
            self.apply_simple_depth_mode("normal")
        return bool(report.get("rows"))

    def simple_run_strategy_comparison(self):
        report = self.build_strategy_comparison_report()
        if len(report.get("rows", [])) < 2:
            return self.start_strategy_dual_run()
        self.latest_strategy_comparison_report = report
        summary = report.get("summary", "实测对比：等待两种策略样本")
        if hasattr(self, "simple_strategy_compare_label"):
            self.simple_strategy_compare_label.setText(summary)
        best = report.get("best", "")
        if best == "完整":
            self.apply_complete_crawl_settings()
        elif best == "深度":
            deep_index = self.simple_depth_combo.findData("deep") if hasattr(self, "simple_depth_combo") else -1
            if deep_index >= 0:
                self.simple_depth_combo.setCurrentIndex(deep_index)
        elif best == "普通":
            normal_index = self.simple_depth_combo.findData("normal") if hasattr(self, "simple_depth_combo") else -1
            if normal_index >= 0:
                self.simple_depth_combo.setCurrentIndex(normal_index)
        if hasattr(self, "simple_progress_label"):
            rows_text = "；".join(
                f"{row.get('strategy')} 完整度{row.get('avg_score')} 链接{row.get('links')}"
                for row in report.get("rows", [])[:3]
            )
            self.simple_progress_label.setText(f"{summary}。{rows_text}")
        return bool(report.get("rows"))

    def refresh_simple_crawl_diagnosis(self):
        if hasattr(self, "simple_diagnosis_label"):
            self.simple_diagnosis_label.setText(self.simple_crawl_diagnosis_text())
        if hasattr(self, "simple_repair_plan_label"):
            self.simple_repair_plan_label.setText(self.simple_repair_plan_text())

    def refresh_simple_result_summary(self):
        if hasattr(self, "simple_result_summary_label"):
            self.simple_result_summary_label.setText(self.simple_result_summary_text())
        self.refresh_simple_crawl_diagnosis()

    def selected_simple_record(self):
        if not hasattr(self, "simple_result_table"):
            return None
        return self.selected_record_from_table(self.simple_result_table)

    def simple_result_counts_text(self, record):
        if not record:
            return "图片 0｜链接 0｜表格 0"
        self.ensure_record_completeness(record)
        return (
            f"图片 {len(record.get('images', []) or [])}"
            f"｜链接 {len(record.get('links', []) or [])}"
            f"｜表格 {len(record.get('tables', []) or [])}"
            f"｜完整度 {record.get('completeness_label') or '0% 偏少'}"
        )

    def update_simple_result_preview(self):
        if not hasattr(self, "simple_preview_title_label"):
            return
        record = self.selected_simple_record()
        if not record:
            self.simple_preview_title_label.setText("未选择结果")
            self.simple_preview_url_label.setText("")
            self.simple_preview_counts_label.setText("图片 0｜链接 0｜表格 0")
            self.simple_preview_body_output.clear()
            return
        self.simple_preview_title_label.setText(record.get("title", "") or "(无标题)")
        self.simple_preview_url_label.setText(record.get("url", ""))
        self.simple_preview_counts_label.setText(self.simple_result_counts_text(record))
        body_text = record.get("body", "")
        if not body_text and record.get("error"):
            body_text = record.get("error", "")
        self.simple_preview_body_output.setPlainText(compact_text(body_text, 1200))

    def simple_export_dir(self):
        export_dir = os.path.join(os.getcwd(), "采集结果导出")
        os.makedirs(export_dir, exist_ok=True)
        return export_dir

    def simple_export_filename(self, prefix):
        stamp = time.strftime("%Y%m%d_%H%M%S")
        return os.path.join(self.simple_export_dir(), f"{prefix}_{stamp}.xlsx")

    def recent_simple_export_files(self, limit=5):
        export_dir = self.simple_export_dir()
        files = []
        for name in os.listdir(export_dir):
            path = os.path.join(export_dir, name)
            if not os.path.isfile(path) or not name.lower().endswith(".xlsx"):
                continue
            files.append(
                {
                    "name": name,
                    "path": path,
                    "mtime": os.path.getmtime(path),
                    "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(path))),
                }
            )
        files.sort(key=lambda item: item.get("mtime", 0), reverse=True)
        return files[: max(1, int(limit or 5))]

    def refresh_simple_recent_area(self):
        if hasattr(self, "simple_recent_files_table"):
            self.simple_recent_files_table.setRowCount(0)
            for source in self.recent_simple_export_files(limit=5):
                row = self.simple_recent_files_table.rowCount()
                self.simple_recent_files_table.insertRow(row)
                values = [source.get("name", ""), source.get("time", ""), source.get("path", "")]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    item.setToolTip(str(value))
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.simple_recent_files_table.setItem(row, column, item)
        if hasattr(self, "simple_recent_records_table"):
            self.simple_recent_records_table.setRowCount(0)
            current_records = list(getattr(self, "records", []) or [])
            history_records = list(getattr(self, "history_records", []) or self.database.recent_records(5))
            records = (list(reversed(current_records)) + history_records)[:5]
            for record in records:
                row = self.simple_recent_records_table.rowCount()
                self.simple_recent_records_table.insertRow(row)
                values = [
                    record.get("title", "") or "(无标题)",
                    record.get("url", ""),
                    record.get("collected_at", ""),
                ]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    item.setToolTip(str(value))
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.simple_recent_records_table.setItem(row, column, item)

    def selected_simple_recent_file_path(self):
        if not hasattr(self, "simple_recent_files_table"):
            return ""
        selected_rows = self.simple_recent_files_table.selectionModel().selectedRows()
        row = selected_rows[0].row() if selected_rows else 0
        if row < 0 or row >= self.simple_recent_files_table.rowCount():
            return ""
        item = self.simple_recent_files_table.item(row, 2)
        return item.text() if item else ""

    def simple_open_path(self, path):
        target = os.path.abspath(path or "")
        if os.environ.get("UNIVERSAL_COLLECTOR_SELF_TEST") == "1":
            self.last_simple_open_path = target
            return True
        if not target or not os.path.exists(target):
            QMessageBox.information(self, "提示", "文件不存在，请先保存一次结果。")
            return False
        return QDesktopServices.openUrl(QUrl.fromLocalFile(target))

    def open_selected_simple_recent_file(self):
        file_path = self.selected_simple_recent_file_path()
        if not file_path:
            QMessageBox.information(self, "提示", "请先选择一个最近保存的 Excel。")
            return False
        return self.simple_open_path(file_path)

    def open_simple_recent_export_folder(self):
        return self.simple_open_path(self.simple_export_dir())

    def simple_information(self, title, message):
        if os.environ.get("UNIVERSAL_COLLECTOR_SELF_TEST") == "1":
            self.last_simple_message = (title, message)
            return
        QMessageBox.information(self, title, message)

    def simple_auto_save_results(self):
        if getattr(self, "records", []):
            columns, rows = self.simple_field_table_data()
            file_path = self.simple_export_filename("按要求整理结果" if columns and rows else "网页采集结果")
            try:
                if columns and rows:
                    export_table_data(file_path, columns, rows, sheet_name="按要求整理结果")
                else:
                    export_records(file_path, self.records)
            except Exception as exc:
                QMessageBox.warning(self, "保存失败", str(exc))
                return False
            self.simple_progress_label.setText(f"已自动保存：{file_path}")
            self.simple_status_label.setText("结果已保存为 Excel")
            self.set_simple_flow_step("导出")
            self.last_simple_export_path = file_path
            self.refresh_simple_recent_area()
            self.simple_information("保存成功", f"已保存：\n{file_path}")
            return True
        columns, rows = self.ai_table_data() if hasattr(self, "ai_table") else ([], [])
        if columns and rows:
            file_path = self.simple_export_filename("文件转表格结果")
            try:
                export_table_data(file_path, columns, rows, sheet_name="文件转表格结果")
            except Exception as exc:
                QMessageBox.warning(self, "保存失败", str(exc))
                return False
            self.simple_progress_label.setText(f"已自动保存：{file_path}")
            self.simple_status_label.setText("表格已保存为 Excel")
            self.set_simple_flow_step("导出")
            self.last_simple_export_path = file_path
            self.refresh_simple_recent_area()
            self.simple_information("保存成功", f"已保存：\n{file_path}")
            return True
        self.simple_information("提示", "还没有可保存的数据。请先开始采集。")
        return False

    def build_overview_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        top_row = QHBoxLayout()
        self.overview_unread_label = QLabel("未读变更：0")
        self.overview_schedule_label = QLabel("计划采集：0")
        self.overview_failed_label = QLabel("异常任务：0")
        self.overview_records_label = QLabel("最近结果：0")
        for label in (
            self.overview_unread_label,
            self.overview_schedule_label,
            self.overview_failed_label,
            self.overview_records_label,
        ):
            label.setMinimumWidth(130)
            top_row.addWidget(label)
        top_row.addStretch(1)
        layout.addLayout(top_row)

        action_row = QHBoxLayout()
        self.overview_new_collect_button = QPushButton("开始新采集")
        self.overview_ai_button = QPushButton("AI 配置/抓取")
        self.overview_alerts_button = QPushButton("查看未读变更")
        self.overview_schedule_button = QPushButton("查看计划采集")
        self.overview_failed_button = QPushButton("查看异常任务")
        self.overview_refresh_button = QPushButton("刷新概览")
        self.overview_new_collect_button.clicked.connect(lambda: self.show_main_tab("批量采集"))
        self.overview_ai_button.clicked.connect(lambda: self.show_main_tab("AI 抓取工作台"))
        self.overview_alerts_button.clicked.connect(lambda: self.show_change_alerts_tab(unread_only=True))
        self.overview_schedule_button.clicked.connect(lambda: self.show_history_section("计划采集"))
        self.overview_failed_button.clicked.connect(lambda: self.show_history_section("任务档案"))
        self.overview_refresh_button.clicked.connect(self.refresh_overview)
        for button in (
            self.overview_new_collect_button,
            self.overview_ai_button,
            self.overview_alerts_button,
            self.overview_schedule_button,
            self.overview_failed_button,
            self.overview_refresh_button,
        ):
            action_row.addWidget(button)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self.overview_status_label = QLabel("等待加载监控概览")
        self.overview_product_boundary_label = QLabel("主产品面向所有网站；旧闲鱼入口仅作为兼容模式保留。")
        self.overview_product_boundary_label.setWordWrap(True)
        layout.addWidget(self.overview_product_boundary_label)
        layout.addWidget(self.overview_status_label)

        self.overview_run_table = QTableWidget(0, 6)
        self.overview_run_table.setHorizontalHeaderLabels(["ID", "时间", "状态", "模板", "结果", "备注"])
        self.overview_run_table.verticalHeader().setVisible(False)
        self.overview_run_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.overview_run_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.overview_run_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.overview_run_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.overview_run_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.overview_run_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(QLabel("最近任务"))
        layout.addWidget(self.overview_run_table, 1)

        self.overview_record_table = QTableWidget(0, 5)
        self.overview_record_table.setHorizontalHeaderLabels(["时间", "网址", "模板", "标题", "错误"])
        self.overview_record_table.verticalHeader().setVisible(False)
        self.overview_record_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.overview_record_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.overview_record_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.overview_record_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.overview_record_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(QLabel("最近结果"))
        layout.addWidget(self.overview_record_table, 1)

        return page

    def setup_notification_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation)
        if icon.isNull():
            icon = QIcon()
        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip(APP_NAME_CN)
        self.tray_icon.activated.connect(self.on_notification_tray_activated)
        self.tray_icon.show()

    def on_notification_tray_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_change_alerts_tab(unread_only=True)

    def show_change_alerts_tab(self, unread_only=False):
        self.show_history_section("变更提醒")
        if unread_only and hasattr(self, "change_alert_filter_combo"):
            self.change_alert_filter_combo.setCurrentText("未读")
        self.show()
        self.raise_()
        self.activateWindow()

    def notify_unread_change_alerts(self, unread_count, latest_alert=None):
        latest_alert = latest_alert or {}
        notice_key = f"{unread_count}:{latest_alert.get('ID', '')}"
        if unread_count <= 0 or notice_key == self.last_unread_alert_notice_key:
            return False
        self.last_unread_alert_notice_key = notice_key
        self.last_unread_alert_notice_count = unread_count
        message = (
            f"发现 {unread_count} 条未读网页变更。"
            f"{latest_alert.get('字段', '')}：{latest_alert.get('旧值', '')} -> {latest_alert.get('新值', '')}"
        )
        self.notification_events.append(
            {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "count": unread_count,
                "id": latest_alert.get("ID", ""),
                "message": message,
            }
        )
        self.append_log(f"[变更通知] {message}")
        if os.environ.get("UNIVERSAL_COLLECTOR_SELF_TEST") == "1":
            return True
        if self.tray_icon:
            self.tray_icon.showMessage(
                "网页变更提醒",
                message,
                QSystemTrayIcon.MessageIcon.Information,
                8000,
            )
        return True

    def overview_metrics(self):
        alerts = getattr(self, "change_alert_rows", []) or []
        schedules = getattr(self, "schedules", []) or []
        runs = getattr(self, "run_records", []) or self.database.recent_runs(20)
        records = getattr(self, "history_records", []) or self.database.recent_records(50)
        unread_alerts = [item for item in alerts if item.get("处理状态") == "未读"]
        enabled_schedules = [item for item in schedules if item.get("enabled")]
        failed_runs = [
            item for item in runs
            if item.get("status") in {"failed", "partial", "stopped"}
        ]
        errored_records = [item for item in records if item.get("error")]
        return {
            "unread_alerts": unread_alerts,
            "schedule_count": len(schedules),
            "enabled_schedule_count": len(enabled_schedules),
            "failed_runs": failed_runs,
            "record_count": len(records),
            "errored_records": errored_records,
            "runs": runs,
            "records": records,
        }

    def fill_overview_run_table(self, runs):
        if not hasattr(self, "overview_run_table"):
            return
        self.overview_run_table.setRowCount(0)
        for run in (runs or [])[:8]:
            row = self.overview_run_table.rowCount()
            self.overview_run_table.insertRow(row)
            values = [
                run.get("id", ""),
                run.get("started_at", ""),
                self.run_status_text(run.get("status", "")),
                run.get("template_name", ""),
                run.get("result_count", 0),
                run.get("notes", ""),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if column == 2 and run.get("status") in {"failed", "partial", "stopped"}:
                    item.setBackground(Qt.GlobalColor.yellow)
                self.overview_run_table.setItem(row, column, item)

    def fill_overview_record_table(self, records):
        if not hasattr(self, "overview_record_table"):
            return
        self.overview_record_table.setRowCount(0)
        for record in (records or [])[:8]:
            row = self.overview_record_table.rowCount()
            self.overview_record_table.insertRow(row)
            values = [
                record.get("collected_at", ""),
                record.get("url", ""),
                record.get("template_name", ""),
                record.get("title", ""),
                record.get("error", ""),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if column == 4 and value:
                    item.setBackground(Qt.GlobalColor.yellow)
                self.overview_record_table.setItem(row, column, item)

    def refresh_overview(self):
        if not hasattr(self, "overview_status_label"):
            return
        metrics = self.overview_metrics()
        unread_count = len(metrics["unread_alerts"])
        failed_count = len(metrics["failed_runs"])
        errored_count = len(metrics["errored_records"])
        self.overview_unread_label.setText(f"未读变更：{unread_count}")
        self.overview_schedule_label.setText(
            f"计划采集：{metrics['enabled_schedule_count']}/{metrics['schedule_count']}"
        )
        self.overview_failed_label.setText(f"异常任务：{failed_count}")
        self.overview_records_label.setText(f"最近结果：{metrics['record_count']}")
        self.overview_status_label.setText(
            "概览已刷新："
            f"未读变更 {unread_count}，异常任务 {failed_count}，结果错误 {errored_count}。"
        )
        self.fill_overview_run_table(metrics["runs"])
        self.fill_overview_record_table(metrics["records"])

    def build_task_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        task_box = QGroupBox("通用采集任务中心")
        task_layout = QGridLayout(task_box)

        self.url_input = QTextEdit()
        self.url_input.setPlaceholderText("每行一个网址，例如：https://example.com/article/1")
        self.url_input.setPlainText("https://example.com/")
        self.import_url_button = QPushButton("导入网址")
        self.import_url_button.clicked.connect(self.import_urls)
        self.template_combo = QComboBox()
        self.use_browser_checkbox = QCheckBox("使用真实浏览器采集动态网页")
        self.use_browser_checkbox.setChecked(True)
        self.keep_login_checkbox = QCheckBox("保留登录状态")
        self.skip_unchanged_checkbox = QCheckBox("跳过未变化重复记录")
        self.skip_unchanged_checkbox.setChecked(True)
        self.subpage_checkbox = QCheckBox("抓取同站子页面")
        self.subpage_limit_input = QSpinBox()
        self.subpage_limit_input.setRange(0, 100)
        self.subpage_limit_input.setValue(0)
        self.scroll_times_input = QSpinBox()
        self.scroll_times_input.setRange(0, 20)
        self.scroll_times_input.setValue(DEFAULT_SCROLL_TIMES)
        self.page_limit_input = QSpinBox()
        self.page_limit_input.setRange(1, 50)
        self.page_limit_input.setValue(DEFAULT_PAGE_LIMIT)
        self.delay_input = QSpinBox()
        self.delay_input.setRange(0, 60)
        self.delay_input.setValue(1)
        self.delay_input.setSuffix(" 秒")

        self.start_button = QPushButton("开始采集")
        self.stop_button = QPushButton("停止")
        self.estimate_task_button = QPushButton("预估任务")
        self.risk_check_button = QPushButton("抓取前检查")
        self.auto_fix_preflight_button = QPushButton("开始前自动修复")
        self.login_browser_button = QPushButton("打开登录浏览器")
        self.stop_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_collecting)
        self.stop_button.clicked.connect(self.stop_collecting)
        self.estimate_task_button.clicked.connect(self.estimate_current_task)
        self.risk_check_button.clicked.connect(self.run_preflight_check)
        self.auto_fix_preflight_button.clicked.connect(self.auto_fix_before_start)
        self.login_browser_button.clicked.connect(self.open_login_browser)

        task_layout.addWidget(QLabel("网址列表"), 0, 0)
        task_layout.addWidget(self.url_input, 1, 0, 1, 4)
        task_layout.addWidget(self.import_url_button, 2, 0)
        task_layout.addWidget(QLabel("模板"), 2, 1)
        task_layout.addWidget(self.template_combo, 2, 2)
        task_layout.addWidget(self.use_browser_checkbox, 2, 3)
        task_layout.addWidget(QLabel("滚动次数"), 3, 0)
        task_layout.addWidget(self.scroll_times_input, 3, 1)
        task_layout.addWidget(QLabel("翻页上限"), 3, 2)
        task_layout.addWidget(self.page_limit_input, 3, 3)
        task_layout.addWidget(QLabel("访问间隔"), 4, 0)
        task_layout.addWidget(self.delay_input, 4, 1)
        task_layout.addWidget(self.start_button, 4, 2)
        task_layout.addWidget(self.stop_button, 4, 3)
        task_layout.addWidget(self.keep_login_checkbox, 5, 0)
        task_layout.addWidget(self.skip_unchanged_checkbox, 5, 1)
        task_layout.addWidget(self.estimate_task_button, 5, 2)
        task_layout.addWidget(self.login_browser_button, 5, 3)
        task_layout.addWidget(self.subpage_checkbox, 6, 0)
        task_layout.addWidget(QLabel("子页面上限"), 6, 1)
        task_layout.addWidget(self.subpage_limit_input, 6, 2)
        task_layout.addWidget(self.risk_check_button, 6, 3)
        task_layout.addWidget(self.auto_fix_preflight_button, 7, 3)

        preview_box = QGroupBox("采集日志")
        preview_layout = QVBoxLayout(preview_box)
        self.collect_progress_bar = QProgressBar()
        self.collect_progress_bar.setRange(0, 100)
        self.collect_progress_bar.setValue(0)
        self.collect_progress_label = QLabel("未开始采集")
        self.collect_progress_label.setWordWrap(True)
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.task_queue_status_filter = QComboBox()
        self.task_queue_status_filter.addItems(["全部状态", "待处理", "预估", "运行中", "已完成", "失败", "未完成"])
        self.task_queue_type_filter = QComboBox()
        self.task_queue_type_filter.addItems(["全部类型", "主页", "分页", "已选子页面", "自动子页面", "实际"])
        self.retry_incomplete_button = QPushButton("重试失败/未完成")
        self.retry_selected_queue_button = QPushButton("重试选中项")
        self.view_queue_result_button = QPushButton("查看队列结果")
        self.copy_queue_error_button = QPushButton("复制错误")
        self.failure_recovery_label = QLabel("失败自恢复：暂无失败项")
        self.failure_recovery_label.setWordWrap(True)
        self.enable_browser_recovery_button = QPushButton("启用真实浏览器")
        self.slow_down_recovery_button = QPushButton("调低速度")
        self.task_queue_status_filter.currentIndexChanged.connect(self.apply_task_queue_filters)
        self.task_queue_type_filter.currentIndexChanged.connect(self.apply_task_queue_filters)
        self.retry_incomplete_button.clicked.connect(self.retry_incomplete_queue_items)
        self.retry_selected_queue_button.clicked.connect(self.retry_selected_queue_item)
        self.view_queue_result_button.clicked.connect(self.view_selected_queue_result)
        self.copy_queue_error_button.clicked.connect(self.copy_selected_queue_error)
        self.enable_browser_recovery_button.clicked.connect(self.enable_browser_recovery)
        self.slow_down_recovery_button.clicked.connect(self.slow_down_recovery)
        self.task_queue_table = QTableWidget(0, 8)
        self.task_queue_table.setHorizontalHeaderLabels(["状态", "类型", "阶段", "网址", "结果数", "错误类型", "建议", "错误"])
        self.task_queue_table.verticalHeader().setVisible(False)
        self.task_queue_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.task_queue_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.task_queue_table.itemSelectionChanged.connect(self.update_queue_detail_panel)
        self.task_queue_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.task_queue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.task_queue_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.task_queue_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.task_queue_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.task_queue_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.task_queue_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.task_queue_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.queue_summary_label = QLabel("队列：0 项")
        self.queue_summary_label.setWordWrap(True)
        self.queue_detail_title_label = QLabel("未选择队列项")
        self.queue_detail_title_label.setWordWrap(True)
        self.queue_detail_output = QPlainTextEdit()
        self.queue_detail_output.setReadOnly(True)
        self.queue_detail_output.setMaximumHeight(110)
        self.risk_table = QTableWidget(0, 5)
        self.risk_table.setHorizontalHeaderLabels(["级别", "检查项", "说明", "建议", "参考"])
        self.risk_table.verticalHeader().setVisible(False)
        self.risk_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.risk_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.risk_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.risk_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.risk_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.risk_summary_label = QLabel("风险摘要：等待抓取前检查")
        self.risk_summary_label.setWordWrap(True)
        preview_layout.addWidget(self.collect_progress_label)
        preview_layout.addWidget(self.collect_progress_bar)
        preview_layout.addWidget(QLabel("任务预估 / 运行队列"))
        queue_filter_layout = QHBoxLayout()
        queue_filter_layout.addWidget(QLabel("状态"))
        queue_filter_layout.addWidget(self.task_queue_status_filter)
        queue_filter_layout.addWidget(QLabel("类型"))
        queue_filter_layout.addWidget(self.task_queue_type_filter)
        queue_filter_layout.addWidget(self.retry_incomplete_button)
        queue_filter_layout.addWidget(self.retry_selected_queue_button)
        queue_filter_layout.addWidget(self.view_queue_result_button)
        queue_filter_layout.addWidget(self.copy_queue_error_button)
        queue_filter_layout.addWidget(self.enable_browser_recovery_button)
        queue_filter_layout.addWidget(self.slow_down_recovery_button)
        queue_filter_layout.addStretch(1)
        preview_layout.addLayout(queue_filter_layout)
        preview_layout.addWidget(self.failure_recovery_label)
        preview_layout.addWidget(self.queue_summary_label)
        preview_layout.addWidget(self.task_queue_table)
        preview_layout.addWidget(self.queue_detail_title_label)
        preview_layout.addWidget(self.queue_detail_output)
        preview_layout.addWidget(self.log_output)
        preview_layout.addWidget(QLabel("抓取前风险/合规检查"))
        preview_layout.addWidget(self.risk_summary_label)
        preview_layout.addWidget(self.risk_table)

        top_splitter.addWidget(task_box)
        top_splitter.addWidget(preview_box)
        top_splitter.setStretchFactor(0, 2)
        top_splitter.setStretchFactor(1, 1)
        layout.addWidget(top_splitter)

        result_box = QGroupBox("本次采集结果")
        result_layout = QVBoxLayout(result_box)
        result_buttons = QHBoxLayout()
        self.export_button = QPushButton("导出结果")
        self.copy_sheets_button = QPushButton("复制到 Sheets")
        self.open_link_button = QPushButton("打开选中链接")
        self.clear_current_button = QPushButton("清空本次结果")
        self.export_button.clicked.connect(self.export_current_results)
        self.copy_sheets_button.clicked.connect(self.copy_current_results_to_sheets)
        self.open_link_button.clicked.connect(self.open_selected_url)
        self.clear_current_button.clicked.connect(self.clear_current_results)
        result_buttons.addWidget(self.export_button)
        result_buttons.addWidget(self.copy_sheets_button)
        result_buttons.addWidget(self.open_link_button)
        result_buttons.addWidget(self.clear_current_button)
        result_buttons.addStretch(1)
        self.result_status_label = QLabel("结果状态：等待采集")
        self.result_status_label.setWordWrap(True)
        self.result_export_hint_label = QLabel("导出引导：采到结果后可导出 Excel 或复制到 Sheets")
        self.result_export_hint_label.setWordWrap(True)
        self.result_table = self.create_result_table()
        self.result_table.itemSelectionChanged.connect(self.update_current_detail)
        result_splitter = QSplitter(Qt.Orientation.Horizontal)
        result_splitter.addWidget(self.result_table)
        result_splitter.addWidget(self.build_detail_panel())
        result_splitter.setStretchFactor(0, 3)
        result_splitter.setStretchFactor(1, 2)
        result_layout.addLayout(result_buttons)
        result_layout.addWidget(self.result_status_label)
        result_layout.addWidget(self.result_export_hint_label)
        result_layout.addWidget(result_splitter)
        layout.addWidget(result_box, 2)

        return page

    def build_detail_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)

        title_box = QGroupBox("结果详情预览")
        title_layout = QGridLayout(title_box)
        self.detail_title_label = QLabel("未选择结果")
        self.detail_title_label.setWordWrap(True)
        self.detail_url_label = QLabel("")
        self.detail_url_label.setWordWrap(True)
        self.detail_meta_label = QLabel("")
        self.detail_meta_label.setWordWrap(True)
        self.detail_body_output = QTextEdit()
        self.detail_body_output.setReadOnly(True)
        self.detail_body_output.setMaximumHeight(150)
        title_layout.addWidget(QLabel("标题"), 0, 0)
        title_layout.addWidget(self.detail_title_label, 0, 1)
        title_layout.addWidget(QLabel("链接"), 1, 0)
        title_layout.addWidget(self.detail_url_label, 1, 1)
        title_layout.addWidget(QLabel("信息"), 2, 0)
        title_layout.addWidget(self.detail_meta_label, 2, 1)
        title_layout.addWidget(QLabel("正文"), 3, 0)
        title_layout.addWidget(self.detail_body_output, 3, 1)

        image_box = QGroupBox("图片缩略图")
        image_layout = QVBoxLayout(image_box)
        self.image_scroll = QScrollArea()
        self.image_scroll.setWidgetResizable(True)
        self.image_container = QWidget()
        self.image_layout = QHBoxLayout(self.image_container)
        self.image_layout.addStretch(1)
        self.image_scroll.setWidget(self.image_container)
        image_layout.addWidget(self.image_scroll)

        table_box = QGroupBox("链接和表格展开")
        table_layout = QVBoxLayout(table_box)
        self.detail_link_table = QTableWidget(0, 2)
        self.detail_link_table.setHorizontalHeaderLabels(["文字", "链接"])
        self.detail_link_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.detail_link_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.detail_link_table.verticalHeader().setVisible(False)
        self.detail_table_view = QTableWidget(0, 0)
        self.detail_table_view.verticalHeader().setVisible(False)
        table_layout.addWidget(QLabel("页面链接"))
        table_layout.addWidget(self.detail_link_table)
        table_layout.addWidget(QLabel("第一个表格"))
        table_layout.addWidget(self.detail_table_view)

        layout.addWidget(title_box)
        layout.addWidget(image_box)
        layout.addWidget(table_box, 1)
        return panel

    def build_template_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.template_list = QListWidget()
        self.template_list.currentRowChanged.connect(self.load_template_to_editor)
        self.template_market_search_input = QLineEdit()
        self.template_market_search_input.setPlaceholderText("搜索行业、字段或用途，例如 电商 / 邮箱 / 图片 / 房产")
        self.template_market_category_combo = QComboBox()
        self.template_market_recommend_label = QLabel("模板市场：等待网址分析")
        self.template_market_recommend_label.setWordWrap(True)
        self.template_market_table = QTableWidget(0, 5)
        self.template_market_table.setHorizontalHeaderLabels(["分类", "模板", "字段数", "模型用途", "说明"])
        self.template_market_table.verticalHeader().setVisible(False)
        self.template_market_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.template_market_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.template_market_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.template_market_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.template_market_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.template_market_install_button = QPushButton("安装选中模板")
        self.template_market_apply_button = QPushButton("安装并用于当前任务")
        self.template_market_search_input.textChanged.connect(self.refresh_template_market)
        self.template_market_category_combo.currentIndexChanged.connect(self.refresh_template_market)
        self.template_market_install_button.clicked.connect(lambda: self.install_market_template(False))
        self.template_market_apply_button.clicked.connect(lambda: self.install_market_template(True))
        self.scene_preset_combo = QComboBox()
        self.apply_scene_preset_button = QPushButton("一键套用场景")
        self.apply_scene_preset_button.clicked.connect(self.apply_scene_preset)
        for name in scene_template_presets().keys():
            self.scene_preset_combo.addItem(name)
        template_buttons = QHBoxLayout()
        self.new_template_button = QPushButton("新建模板")
        self.save_template_button = QPushButton("保存模板")
        self.delete_template_button = QPushButton("删除模板")
        self.new_template_button.clicked.connect(self.new_template)
        self.save_template_button.clicked.connect(self.save_current_template)
        self.delete_template_button.clicked.connect(self.delete_current_template)
        template_buttons.addWidget(self.new_template_button)
        template_buttons.addWidget(self.save_template_button)
        template_buttons.addWidget(self.delete_template_button)
        left_layout.addWidget(self.template_list)
        left_layout.addWidget(QLabel("模板市场"))
        left_layout.addWidget(self.template_market_recommend_label)
        left_layout.addWidget(self.template_market_search_input)
        left_layout.addWidget(self.template_market_category_combo)
        left_layout.addWidget(self.template_market_table, 1)
        market_buttons = QHBoxLayout()
        market_buttons.addWidget(self.template_market_install_button)
        market_buttons.addWidget(self.template_market_apply_button)
        left_layout.addLayout(market_buttons)
        left_layout.addWidget(QLabel("场景模板库"))
        left_layout.addWidget(self.scene_preset_combo)
        left_layout.addWidget(self.apply_scene_preset_button)
        left_layout.addLayout(template_buttons)

        editor_box = QGroupBox("模板编辑")
        editor_layout = QGridLayout(editor_box)
        self.template_name_input = QLineEdit()
        self.template_domain_input = QLineEdit()
        self.template_type_combo = QComboBox()
        for key, text in TEMPLATE_TYPES.items():
            self.template_type_combo.addItem(text, key)
        self.next_page_selector_input = QLineEdit()
        self.next_page_selector_input.setPlaceholderText("可选，例如：a.next, .pagination-next")
        self.template_notes_input = QTextEdit()
        self.template_notes_input.setMaximumHeight(80)

        self.field_table = QTableWidget(0, 4)
        self.field_table.setHorizontalHeaderLabels(["字段名", "CSS 选择器", "取值", "多条"])
        self.field_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.field_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.field_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.field_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        field_buttons = QHBoxLayout()
        self.add_field_button = QPushButton("添加字段")
        self.remove_field_button = QPushButton("删除字段")
        self.selector_helper_button = QPushButton("点选结果转选择器")
        self.visual_pick_button = QPushButton("打开网页点选字段")
        self.add_field_button.clicked.connect(self.add_field_row)
        self.remove_field_button.clicked.connect(self.remove_selected_field)
        self.selector_helper_button.clicked.connect(self.generate_selector_from_helper)
        self.visual_pick_button.clicked.connect(self.visual_pick_field)
        field_buttons.addWidget(self.add_field_button)
        field_buttons.addWidget(self.remove_field_button)
        field_buttons.addWidget(self.selector_helper_button)
        field_buttons.addWidget(self.visual_pick_button)
        field_buttons.addStretch(1)

        self.pick_url_input = QLineEdit()
        self.pick_url_input.setPlaceholderText("点选网址，留空则使用采集任务里的第一个网址")
        self.pick_field_name_input = QLineEdit()
        self.pick_field_name_input.setPlaceholderText("字段名，例如 标题 / 价格 / 图片")
        self.click_tag_input = QLineEdit()
        self.click_tag_input.setPlaceholderText("点选元素标签，例如 div / h1 / img")
        self.click_id_input = QLineEdit()
        self.click_id_input.setPlaceholderText("元素 id，可空")
        self.click_class_input = QLineEdit()
        self.click_class_input.setPlaceholderText("元素 class，用空格分隔，可空")

        editor_layout.addWidget(QLabel("模板名称"), 0, 0)
        editor_layout.addWidget(self.template_name_input, 0, 1)
        editor_layout.addWidget(QLabel("匹配域名"), 0, 2)
        editor_layout.addWidget(self.template_domain_input, 0, 3)
        editor_layout.addWidget(QLabel("模板类型"), 1, 0)
        editor_layout.addWidget(self.template_type_combo, 1, 1)
        editor_layout.addWidget(QLabel("下一页选择器"), 1, 2)
        editor_layout.addWidget(self.next_page_selector_input, 1, 3)
        editor_layout.addWidget(QLabel("说明"), 2, 0)
        editor_layout.addWidget(self.template_notes_input, 2, 1, 1, 3)
        editor_layout.addWidget(self.field_table, 3, 0, 1, 4)
        editor_layout.addLayout(field_buttons, 4, 0, 1, 4)
        editor_layout.addWidget(QLabel("点选网址"), 5, 0)
        editor_layout.addWidget(self.pick_url_input, 5, 1, 1, 2)
        editor_layout.addWidget(self.pick_field_name_input, 5, 3)
        editor_layout.addWidget(QLabel("点选结果"), 6, 0)
        editor_layout.addWidget(self.click_tag_input, 6, 1)
        editor_layout.addWidget(self.click_id_input, 6, 2)
        editor_layout.addWidget(self.click_class_input, 6, 3)

        splitter.addWidget(left)
        splitter.addWidget(editor_box)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter)
        return page

    def create_result_table(self):
        table = QTableWidget(0, len(FIELD_HEADERS))
        table.setHorizontalHeaderLabels(FIELD_HEADERS)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for index in range(2, len(FIELD_HEADERS)):
            table.horizontalHeader().setSectionResizeMode(index, QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        return table

    def create_simple_result_table(self):
        table = QTableWidget(0, 7)
        table.setHorizontalHeaderLabels(["状态", "标题", "内容", "网址", "图片", "完整度", "错误"])
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(5, 138)
        table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        return table

    def completeness_score_color(self, score):
        score = int(score or 0)
        if score >= 85:
            return "#16a34a"
        if score >= 60:
            return "#d97706"
        return "#dc2626"

    def completeness_bar_widget(self, record):
        self.ensure_record_completeness(record)
        score = max(0, min(100, int(record.get("completeness_score") or 0)))
        label = record.get("completeness_label") or f"{score}%"
        missing = "、".join(record.get("completeness_missing", []) or [])
        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setValue(score)
        progress.setFormat(label)
        progress.setTextVisible(True)
        color = self.completeness_score_color(score)
        progress.setToolTip(f"{label}" + (f"\n缺少：{missing}" if missing else "\n资料较完整"))
        progress.setStyleSheet(
            f"""
            QProgressBar {{
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                background: #f8fafc;
                text-align: center;
                color: #111827;
                font-weight: 600;
                min-height: 18px;
            }}
            QProgressBar::chunk {{
                background: {color};
                border-radius: 3px;
            }}
            """
        )
        return progress

    def simple_missing_hint(self, record):
        self.ensure_record_completeness(record)
        missing = record.get("completeness_missing", []) or []
        if not missing:
            return "资料较完整"
        hint = "缺少：" + "、".join(missing[:4])
        if len(missing) > 4:
            hint += f"等 {len(missing)} 项"
        return hint

    def add_record_to_simple_table(self, record, record_index=None):
        if not hasattr(self, "simple_result_table"):
            return
        self.ensure_record_completeness(record)
        row = self.simple_result_table.rowCount()
        self.simple_result_table.insertRow(row)
        body_preview = compact_text(record.get("body", ""), 160)
        if not body_preview and record.get("tables"):
            body_preview = "已抓到表格"
        if not body_preview and record.get("links"):
            body_preview = f"已抓到 {len(record.get('links') or [])} 个链接"
        values = [
            self.record_status_text(record),
            record.get("title", "") or "(无标题)",
            body_preview,
            record.get("url", ""),
            str(len(record.get("images", []) or [])),
            record.get("completeness_label", ""),
            record.get("error", ""),
        ]
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setToolTip(str(value))
            if column == 1:
                item.setToolTip(f"{value}\n{self.simple_missing_hint(record)}")
            if column == 5:
                item.setToolTip(self.simple_missing_hint(record))
            if column == 0:
                item.setData(Qt.ItemDataRole.UserRole, "current")
                item.setData(
                    Qt.ItemDataRole.UserRole + 1,
                    record_index if record_index is not None else row,
                )
            self.simple_result_table.setItem(row, column, item)
        self.simple_result_table.setCellWidget(row, 5, self.completeness_bar_widget(record))
        self.style_simple_record_row(row, record)

    def simple_refresh_result_row(self, row, record, record_index=None):
        if not hasattr(self, "simple_result_table") or row < 0 or row >= self.simple_result_table.rowCount():
            return
        self.ensure_record_completeness(record)
        body_preview = compact_text(record.get("body", ""), 160)
        if not body_preview and record.get("tables"):
            body_preview = "已抓到表格"
        if not body_preview and record.get("links"):
            body_preview = f"已抓到 {len(record.get('links') or [])} 个链接"
        values = [
            self.record_status_text(record),
            record.get("title", "") or "(无标题)",
            body_preview,
            record.get("url", ""),
            str(len(record.get("images", []) or [])),
            record.get("completeness_label", ""),
            record.get("error", ""),
        ]
        for column, value in enumerate(values):
            item = self.simple_result_table.item(row, column)
            if item is None:
                item = QTableWidgetItem()
                self.simple_result_table.setItem(row, column, item)
            item.setText(str(value))
            item.setToolTip(str(value))
            if column == 1:
                item.setToolTip(f"{value}\n{self.simple_missing_hint(record)}")
            if column == 5:
                item.setToolTip(self.simple_missing_hint(record))
            if column == 0:
                item.setData(Qt.ItemDataRole.UserRole, "current")
                item.setData(Qt.ItemDataRole.UserRole + 1, record_index if record_index is not None else row)
        self.simple_result_table.setCellWidget(row, 5, self.completeness_bar_widget(record))
        self.style_simple_record_row(row, record)

    def simple_record_link_urls(self, record):
        urls = []
        for link in record.get("links", []) or []:
            raw_url = link.get("url", "") if isinstance(link, dict) else str(link)
            normalized = normalize_url(raw_url, record.get("url", ""))
            if normalized and normalized not in urls:
                urls.append(normalized)
        return urls

    def simple_find_parent_record_index(self, record):
        target_url = normalize_url(record.get("url", ""))
        if not target_url:
            return -1
        cached = getattr(self, "simple_subpage_parent_map", {}).get(target_url)
        if isinstance(cached, int) and 0 <= cached < len(self.records):
            return cached
        for index, source in enumerate(self.records):
            if source is record:
                continue
            if target_url in self.simple_record_link_urls(source):
                self.simple_subpage_parent_map[target_url] = index
                return index
        return -1

    def simple_unique_list(self, items):
        result = []
        seen = set()
        for item in items or []:
            key = json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, dict) else str(item)
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    def simple_merge_subpage_into_parent(self, parent, child):
        changed = False
        if child.get("body") and child.get("body") not in (parent.get("body") or ""):
            parent["body"] = compact_text(((parent.get("body") or "") + "\n\n" + child.get("body", "")).strip(), 5000)
            changed = True
        for scalar_key in ("price", "published_time", "author"):
            if not parent.get(scalar_key) and child.get(scalar_key):
                parent[scalar_key] = child.get(scalar_key)
                changed = True
        for list_key in ("images", "links", "tables"):
            before_count = len(parent.get(list_key, []) or [])
            parent[list_key] = self.simple_unique_list((parent.get(list_key, []) or []) + (child.get(list_key, []) or []))
            if len(parent.get(list_key, []) or []) != before_count:
                changed = True
        if changed:
            parent["simple_detail_enriched"] = True
            parent["simple_detail_urls"] = self.simple_unique_list((parent.get("simple_detail_urls", []) or []) + [child.get("url", "")])
        return changed

    def style_simple_record_row(self, row, record):
        if not hasattr(self, "simple_result_table"):
            return
        status = self.record_status_text(record)
        self.ensure_record_completeness(record)
        score = int(record.get("completeness_score") or 0)
        palette = {
            "错误": ("#fff1f0", "#a8071a"),
            "变化": ("#fffbe6", "#ad6800"),
            "重复": ("#f5f5f5", "#595959"),
            "新增": ("#f6ffed", "#237804"),
        }
        background, foreground = palette.get(status, ("#ffffff", "#262626"))
        if status == "新增":
            if score < 60:
                background, foreground = ("#fff1f0", "#a8071a")
            elif score < 85:
                background, foreground = ("#fffbe6", "#ad6800")
        for column in range(self.simple_result_table.columnCount()):
            item = self.simple_result_table.item(row, column)
            if not item:
                continue
            item.setBackground(QColor(background))
            if column == 0:
                item.setForeground(QColor(foreground))
                item.setToolTip(f"{status}｜{record.get('completeness_label', '')}\n{self.simple_missing_hint(record)}")

    def append_log(self, message):
        self.record_crawl_discovery_message(message)
        if hasattr(self, "log_output"):
            self.log_output.append(message)
        if hasattr(self, "simple_status_label"):
            self.simple_status_label.setText(str(message))
        if hasattr(self, "ai_output"):
            self.ai_output.appendPlainText(str(message))

    def record_crawl_discovery_message(self, message):
        text = str(message or "")
        if not text.startswith(("自动翻页候选", "自动发现", "子页面发现", "发现 ")):
            return
        if "自动翻页" not in text and "分页" not in text and "子页面" not in text:
            return
        messages = list(getattr(self, "latest_crawl_discovery_messages", []) or [])
        messages.append(compact_text(text, 220))
        self.latest_crawl_discovery_messages = messages[-4:]
        if hasattr(self, "simple_discovery_label"):
            self.simple_discovery_label.setText("发现记录：" + " ｜ ".join(self.latest_crawl_discovery_messages))

    def append_ai_output(self, message):
        self.ai_output.appendPlainText(str(message))

    def load_ai_settings_to_ui(self):
        settings = self.ai_settings
        self._loading_ai_settings = True
        provider = settings.get("provider") or "openai"
        provider_index = self.ai_provider_combo.findData(provider)
        self.ai_provider_combo.setCurrentIndex(max(0, provider_index))
        self.current_ai_provider = provider
        self.load_provider_settings_to_ui(settings)
        self._loading_ai_settings = False

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
        self.ai_key_input.setText(settings.get("api_key", ""))
        self.ai_key_name_input.setText(settings.get("active_api_key_name", "") or "默认 Key")
        self.ai_key_entries = normalize_api_key_entries(
            settings.get("api_keys"),
            settings.get("api_key", ""),
            settings.get("active_api_key_name", ""),
        )
        if hasattr(self, "ai_auto_apply_use_case_checkbox"):
            self.ai_auto_apply_use_case_checkbox.setChecked(settings.get("auto_apply_use_case", True) is not False)
        self.refresh_ai_key_combo(settings.get("active_api_key_name", ""))
        self.update_ai_provider_boundary(settings)
        self.refresh_api_health_summary()
        self.refresh_ai_provider_overview()
        self.refresh_ai_repair_history()

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

    def unique_models(self, models):
        return unique_model_names(models)

    def clean_model_display_text(self, text):
        text = str(text or "").strip()
        while text.startswith("[") and "]" in text:
            text = text.split("]", 1)[1].strip()
        return text

    def current_ai_model_text(self):
        current_text = self.ai_model_combo.currentText().strip()
        index = self.ai_model_combo.currentIndex()
        data = self.ai_model_combo.currentData() if index >= 0 else ""
        if data and current_text == self.ai_model_combo.itemText(index):
            return str(data).strip()
        return self.clean_model_display_text(current_text)

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

    def refresh_api_health_summary(self, diagnosis=None):
        if hasattr(self, "api_health_label"):
            self.api_health_label.setText(self.api_health_summary_text(diagnosis))

    def refresh_ai_provider_overview(self):
        if not hasattr(self, "ai_provider_overview_table") or not hasattr(self, "ai_key_input"):
            return
        try:
            latest_settings = load_ai_settings()
        except Exception:
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

    def selected_ai_provider_from_overview(self):
        table = getattr(self, "ai_provider_overview_table", None)
        if not table:
            return ""
        selected = table.selectedIndexes()
        if not selected:
            return ""
        item = table.item(selected[0].row(), 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else ""

    def switch_ai_provider_from_overview_item(self, item):
        provider = item.data(Qt.ItemDataRole.UserRole) if item else ""
        self.switch_ai_provider_from_overview(provider)

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

    def model_display_text(self, model):
        provider = self.ai_provider_combo.currentData() if hasattr(self, "ai_provider_combo") else ""
        tags = model_tags(model, provider)
        prefix = " ".join(f"[{tag}]" for tag in tags)
        return f"{prefix} {model}".strip()

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

    def filter_ai_models(self):
        if getattr(self, "_loading_ai_settings", False):
            return
        self.refresh_ai_model_combo()

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

    def toggle_ai_key_visibility(self):
        if self.ai_key_input.echoMode() == QLineEdit.EchoMode.Password:
            self.ai_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.ai_key_show_button.setText("隐藏")
        else:
            self.ai_key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.ai_key_show_button.setText("显示")

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

    def collect_ai_settings_from_ui(self, provider_override=None):
        provider = provider_override or self.ai_provider_combo.currentData() or "custom"
        models = [
            model for model in self.ai_model_cache
        ]
        current_model = self.current_ai_model_text()
        if current_model and current_model not in models:
            models.insert(0, current_model)
        key_name = self.ai_key_name_input.text().strip() or "默认 Key"
        api_key = self.ai_key_input.text().strip()
        entries = [dict(item) for item in getattr(self, "ai_key_entries", [])]
        if api_key:
            replaced = False
            for entry in entries:
                if entry.get("name") == key_name:
                    entry["key"] = api_key
                    replaced = True
                    break
            if not replaced:
                entries.append({"name": key_name, "key": api_key})
        entries = normalize_api_key_entries(entries, "", key_name)
        saved_provider_settings = {}
        if isinstance(self.ai_settings, dict):
            saved_provider_settings = (self.ai_settings.get("providers") or {}).get(provider, {})
        return {
            "provider": provider,
            "provider_name": AI_PROVIDER_PRESETS.get(provider, {}).get("name", provider),
            "api_format": self.ai_format_combo.currentData() or "openai_compatible",
            "base_url": self.ai_base_url_input.text().strip(),
            "models_url": self.ai_models_url_input.text().strip(),
            "model": current_model,
            "models": models,
            "model_cache": models,
            "api_key": api_key,
            "api_keys": entries,
            "active_api_key_name": key_name if api_key else (entries[0]["name"] if entries else ""),
            "auto_apply_use_case": self.ai_auto_apply_use_case_checkbox.isChecked()
            if hasattr(self, "ai_auto_apply_use_case_checkbox")
            else True,
            "models_updated_at": saved_provider_settings.get("models_updated_at", ""),
            "models_refresh_error": saved_provider_settings.get("models_refresh_error", ""),
            "connection_status": saved_provider_settings.get("connection_status", "未测试"),
            "connection_tested_at": saved_provider_settings.get("connection_tested_at", ""),
            "connection_error": saved_provider_settings.get("connection_error", ""),
            "temperature": 0.1,
            "timeout_seconds": 60,
        }

    def on_ai_provider_changed(self):
        provider = self.ai_provider_combo.currentData() or "custom"
        if self._loading_ai_settings:
            return
        previous_provider = getattr(self, "current_ai_provider", "")
        if previous_provider and previous_provider != provider:
            self.ai_settings = save_ai_settings(
                self.collect_ai_settings_from_ui(provider_override=previous_provider)
            )
        provider_settings = (self.ai_settings.get("providers") or {}).get(provider)
        if not provider_settings:
            provider_settings = ai_preset_for(provider)
            provider_settings = {
                "provider": provider,
                "provider_name": provider_settings.get("name", provider),
                "api_format": provider_settings.get("api_format", "openai_compatible"),
                "base_url": provider_settings.get("base_url", ""),
                "models_url": provider_settings.get("models_url", ""),
                "model": provider_settings.get("default_model", ""),
                "models": provider_settings.get("models", []),
                "api_key": "",
                "temperature": 0.1,
                "timeout_seconds": 60,
            }
        self._loading_ai_settings = True
        self.load_provider_settings_to_ui(provider_settings)
        self._loading_ai_settings = False
        self.current_ai_provider = provider
        self.refresh_api_health_summary()

    def save_ai_settings_from_ui(self):
        current_model = self.current_ai_model_text()
        if current_model:
            self.ai_model_cache = self.unique_models([current_model] + self.ai_model_cache)
        self.ai_settings = save_ai_settings(self.collect_ai_settings_from_ui())
        self.current_ai_provider = self.ai_settings.get("provider", self.current_ai_provider)
        self.append_ai_output(f"已保存当前厂商 API Key、Base URL 和模型：{AI_SETTINGS_FILE}")
        self.refresh_api_health_summary()
        self.refresh_ai_provider_overview()

    def apply_recommended_ai_settings(self):
        provider = self.ai_provider_combo.currentData() or "custom"
        preset = ai_preset_for(provider)
        current_api_key = self.ai_key_input.text().strip()
        current_key_name = self.ai_key_name_input.text().strip() or "默认 Key"
        current_key_entries = normalize_api_key_entries(getattr(self, "ai_key_entries", []), current_api_key, current_key_name)
        current_models = self.unique_models(self.ai_model_cache)
        preset_models = self.unique_models(preset.get("models", []))
        default_model = preset.get("default_model") or (preset_models[0] if preset_models else "")
        fixed_settings = {
            "provider": provider,
            "provider_name": preset.get("name", provider),
            "api_format": preset.get("api_format", "openai_compatible"),
            "base_url": preset.get("base_url", ""),
            "models_url": preset.get("models_url", ""),
            "model": default_model,
            "models": self.unique_models(preset_models + current_models),
            "model_cache": self.unique_models(preset_models + current_models),
            "api_key": current_api_key,
            "api_keys": current_key_entries,
            "active_api_key_name": current_key_name if current_api_key else (current_key_entries[0]["name"] if current_key_entries else ""),
            "auto_apply_use_case": self.ai_auto_apply_use_case_checkbox.isChecked()
            if hasattr(self, "ai_auto_apply_use_case_checkbox")
            else True,
            "temperature": 0.1,
            "timeout_seconds": 60,
        }
        self.ai_settings = save_ai_settings(fixed_settings)
        provider_settings = (self.ai_settings.get("providers") or {}).get(provider, fixed_settings)
        self._loading_ai_settings = True
        self.load_provider_settings_to_ui(provider_settings)
        self._loading_ai_settings = False
        self.current_ai_provider = provider
        diagnosis = diagnose_ai_settings(self.collect_ai_settings_from_ui())
        self.fill_ai_diagnosis_table(diagnosis.get("checks", []))
        self.refresh_api_health_summary(diagnosis)
        self.append_ai_output(f"已应用 {preset.get('name', provider)} 推荐配置，并保留当前 API Key。{diagnosis.get('summary', '')}")
        self.refresh_ai_provider_overview()

    def apply_ai_use_case_preset(self):
        use_case_key = self.ai_use_case_combo.currentData() or "web_scrape"
        use_case = AI_MODEL_USE_CASE_PRESETS.get(use_case_key) or AI_MODEL_USE_CASE_PRESETS["web_scrape"]
        provider = use_case.get("provider") or "openai"
        model = use_case.get("model") or ""
        provider_index = self.ai_provider_combo.findData(provider)
        if provider_index < 0:
            QMessageBox.information(self, "提示", f"用途预设需要的厂商不存在：{provider}")
            return
        current_api_key = self.ai_key_input.text().strip()
        current_key_name = self.ai_key_name_input.text().strip() or "默认 Key"
        current_key_entries = normalize_api_key_entries(getattr(self, "ai_key_entries", []), current_api_key, current_key_name)
        self.ai_provider_combo.setCurrentIndex(provider_index)
        preset = ai_preset_for(provider)
        preset_models = self.unique_models(preset.get("models", []))
        model_cache = self.unique_models([model] + preset_models + self.ai_model_cache)
        fixed_settings = {
            "provider": provider,
            "provider_name": preset.get("name", provider),
            "api_format": preset.get("api_format", "openai_compatible"),
            "base_url": preset.get("base_url", ""),
            "models_url": preset.get("models_url", ""),
            "model": model or preset.get("default_model", ""),
            "models": model_cache,
            "model_cache": model_cache,
            "api_key": current_api_key,
            "api_keys": current_key_entries,
            "active_api_key_name": current_key_name if current_api_key else (current_key_entries[0]["name"] if current_key_entries else ""),
            "auto_apply_use_case": self.ai_auto_apply_use_case_checkbox.isChecked()
            if hasattr(self, "ai_auto_apply_use_case_checkbox")
            else True,
            "temperature": 0.1,
            "timeout_seconds": 60,
        }
        self.ai_settings = save_ai_settings(fixed_settings)
        provider_settings = (self.ai_settings.get("providers") or {}).get(provider, fixed_settings)
        self._loading_ai_settings = True
        self.load_provider_settings_to_ui(provider_settings)
        self._loading_ai_settings = False
        self.current_ai_provider = provider
        self.ai_model_search_input.clear()
        self.refresh_ai_model_combo(model or provider_settings.get("model", ""))
        diagnosis = diagnose_ai_settings(self.collect_ai_settings_from_ui())
        self.fill_ai_diagnosis_table(diagnosis.get("checks", []))
        self.refresh_api_health_summary(diagnosis)
        self.append_ai_output(
            f"已按用途“{use_case.get('name')}”选择 {preset.get('name', provider)} / {self.current_ai_model_text()}。{use_case.get('goal', '')}"
        )
        self.refresh_ai_provider_overview()

    def run_ai_worker(self, action, payload=None):
        if self.ai_worker:
            QMessageBox.information(self, "提示", "已有 AI 任务正在运行，请稍等。")
            return
        self.save_ai_settings_from_ui()
        self.ai_thread = QThread(self)
        self.ai_worker = AIWorker(action, self.ai_settings, payload or {})
        self.ai_worker.moveToThread(self.ai_thread)
        self.ai_thread.started.connect(self.ai_worker.run)
        self.ai_worker.log_signal.connect(self.append_ai_output)
        self.ai_worker.result_signal.connect(self.on_ai_result)
        self.ai_worker.finished_signal.connect(self.ai_thread.quit)
        self.ai_worker.finished_signal.connect(self.ai_worker.deleteLater)
        self.ai_thread.finished.connect(self.ai_thread.deleteLater)
        self.ai_thread.finished.connect(self.on_ai_finished)
        self.append_ai_output(f"开始 AI 任务：{action}")
        self.ai_thread.start()

    def start_image_download(self, records, target_dir, context="ai"):
        if self.image_download_thread:
            if context == "simple" and hasattr(self, "simple_status_label"):
                self.simple_status_label.setText("图片正在后台下载，请稍等")
            else:
                QMessageBox.information(self, "提示", "图片正在后台下载，请稍等。")
            return False
        self.image_download_context = context
        self.latest_image_download_rows = []
        if context == "simple":
            if hasattr(self, "simple_status_label"):
                self.simple_status_label.setText("图片正在后台下载")
            if hasattr(self, "simple_progress_label"):
                self.simple_progress_label.setText(f"后台：图片会保存到 {target_dir}")
            if hasattr(self, "simple_image_button"):
                self.simple_image_button.setEnabled(False)
                self.simple_image_button.setText("下载中")
        self.image_download_thread = QThread(self)
        self.image_download_worker = ImageDownloadWorker(records, target_dir)
        self.image_download_worker.moveToThread(self.image_download_thread)
        self.image_download_thread.started.connect(self.image_download_worker.run)
        self.image_download_worker.log_signal.connect(self.append_ai_output)
        self.image_download_worker.result_signal.connect(self.on_image_download_result)
        self.image_download_worker.finished_signal.connect(self.image_download_thread.quit)
        self.image_download_worker.finished_signal.connect(self.image_download_worker.deleteLater)
        self.image_download_thread.finished.connect(self.image_download_thread.deleteLater)
        self.image_download_thread.finished.connect(self.on_image_download_finished)
        self.append_ai_output(f"开始后台下载图片：{target_dir}")
        self.image_download_thread.start()
        return True

    def on_image_download_result(self, saved, target_dir):
        saved = list(saved or [])
        self.latest_image_download_rows = saved
        rows = [
            [
                item.get("status", ""),
                item.get("file_path", ""),
                item.get("image_url", ""),
                item.get("source_title", ""),
                item.get("source_url", ""),
                item.get("size_bytes", ""),
                item.get("error", ""),
            ]
            for item in saved
        ]
        self.fill_ai_table(["状态", "保存路径", "图片网址", "来源标题", "来源网址", "大小字节", "错误"], rows)
        saved_count = sum(1 for item in saved if item.get("status") == "已保存")
        failed_count = sum(1 for item in saved if item.get("status") != "已保存")
        self.append_ai_output(f"图片下载完成：成功 {saved_count} 张，失败 {failed_count} 张。")
        context = getattr(self, "image_download_context", "")
        if context == "simple":
            if hasattr(self, "simple_status_label"):
                self.simple_status_label.setText(f"图片下载完成：成功 {saved_count} 张，失败 {failed_count} 张")
            if hasattr(self, "simple_progress_label"):
                self.simple_progress_label.setText(f"图片保存位置：{target_dir}")
            self.simple_information("图片下载完成", f"成功 {saved_count} 张，失败 {failed_count} 张。\n{target_dir}")
        else:
            QMessageBox.information(self, "图片下载完成", f"成功 {saved_count} 张，失败 {failed_count} 张。结果已放入 AI 表格，可导出或复制。")
            self.show_ai_json({"saved": saved})

    def on_image_download_finished(self):
        if hasattr(self, "simple_image_button"):
            self.simple_image_button.setEnabled(True)
            self.simple_image_button.setText("下载图片")
        self.image_download_thread = None
        self.image_download_worker = None
        self.image_download_context = ""
        self.append_ai_output("图片下载任务结束。")

    def on_ai_finished(self):
        self.ai_worker = None
        self.ai_thread = None
        self.refresh_ai_call_logs()
        self.append_ai_output("AI 任务结束。")

    def first_target_url(self):
        url = normalize_url(self.ai_url_input.text())
        if url:
            return url
        urls = self.urls_from_input()
        return urls[0] if urls else ""

    def fetch_snapshot_html(self, url):
        return UniversalCollector(logger=self.append_ai_output).fetch_with_playwright(
            url,
            scroll_times=self.scroll_times_input.value(),
            keep_login_state=self.keep_login_checkbox.isChecked(),
        )

    def test_ai_api(self):
        self.run_ai_worker("test_api")

    def diagnose_ai_api(self):
        self.run_ai_worker("diagnose_api")

    def fetch_ai_models(self):
        self.run_ai_worker("fetch_models")

    def refresh_all_ai_provider_models(self):
        self.save_ai_settings_from_ui()
        self.run_ai_worker("refresh_provider_models", {"providers": list(AI_PROVIDER_PRESETS.keys())})

    def test_all_ai_provider_connectivity(self):
        self.save_ai_settings_from_ui()
        self.run_ai_worker("test_provider_connectivity", {"providers": list(AI_PROVIDER_PRESETS.keys())})

    def ai_suggest_fields_for_current_url(self):
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
            except Exception:
                return ""
        return ""

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

    def configure_collect_wizard(self):
        url = normalize_url(self.ai_url_input.text()) or self.first_target_url()
        if url:
            self.ai_url_input.setText(url)
            self.url_input.setPlainText(url)
            self.pick_url_input.setText(url)
        preset_name = self.wizard_scene_combo.currentText()
        if not scene_template_presets().get(preset_name):
            QMessageBox.information(self, "提示", "请选择一个场景。")
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

    def prepare_two_click_collect(self):
        url = self.first_target_url()
        if not url:
            QMessageBox.information(self, "提示", "请先输入要抓取的网址。")
            return False
        self.configure_collect_wizard()
        if not isinstance(self.latest_ai_result, dict):
            QMessageBox.information(self, "提示", "向导还没有生成可用计划。")
            return False
        if not self.apply_current_ai_task_plan():
            return False
        urls = self.urls_from_input()
        queue = self.estimated_task_queue(urls)
        self.fill_task_queue_table(queue)
        risks = self.run_preflight_check()
        risk_text = self.risk_summary_text(risks)
        self.show_main_tab("批量采集")
        self.collect_progress_label.setText(
            f"2 次点击准备完成：已生成模板、预采评分、任务队列和风险摘要。{risk_text}"
        )
        self.append_ai_output(
            f"2 次点击准备完成：模板 {self.selected_template_name()}，网址 {len(urls)} 个，队列 {len(queue)} 项。{risk_text}"
        )
        self.append_log("AI 工作台已准备好采集任务；检查队列后可开始采集。")
        self.refresh_new_user_flow_status("prepared")
        return True

    def prepare_and_start_collect(self):
        if self.worker:
            self.append_log("已有采集任务正在运行，未重复启动。")
            return False
        if not self.prepare_two_click_collect():
            return False
        self.append_log("AI 工作台已准备完成，正在开始采集。")
        self.refresh_new_user_flow_status("running")
        self.start_collecting()
        return True

    def apply_wizard_use_case(self, plan):
        if not isinstance(plan, dict):
            return False
        use_case = plan.get("use_case") or {}
        use_case_key = use_case.get("key") or ""
        if not use_case_key:
            return False
        use_case_index = self.ai_use_case_combo.findData(use_case_key)
        if use_case_index < 0:
            return False
        self.ai_use_case_combo.setCurrentIndex(use_case_index)
        if (
            hasattr(self, "ai_auto_apply_use_case_checkbox")
            and not self.ai_auto_apply_use_case_checkbox.isChecked()
        ):
            self.append_ai_output(
                f"向导推荐模型用途：{use_case.get('name') or self.ai_use_case_combo.currentText()}；已保留当前手动模型。"
            )
            return True
        self.apply_ai_use_case_preset()
        self.append_ai_output(f"向导已自动选择模型用途：{use_case.get('name') or self.ai_use_case_combo.currentText()}")
        return True

    def apply_market_recommendation_from_plan(self, plan):
        if not hasattr(self, "template_market_table") or not isinstance(plan, dict):
            return False
        recommendations = recommend_template_market_items(plan=plan, limit=5)
        if not recommendations:
            self.template_market_recommend_label.setText("模板市场：未找到匹配模板")
            return False
        top = recommendations[0]
        template = top.get("template") or SiteTemplate(top.get("name", ""))
        use_case_key = top.get("recommended_use_case") or ""
        use_case_name = AI_MODEL_USE_CASE_PRESETS.get(use_case_key, {}).get("name", use_case_key)
        self.template_market_search_input.blockSignals(True)
        self.template_market_search_input.setText(template.name)
        self.template_market_search_input.blockSignals(False)
        all_index = self.template_market_category_combo.findText("全部分类")
        if all_index >= 0:
            self.template_market_category_combo.blockSignals(True)
            self.template_market_category_combo.setCurrentIndex(all_index)
            self.template_market_category_combo.blockSignals(False)
        self.refresh_template_market()
        for row, item in enumerate(getattr(self, "template_market_items", [])):
            candidate = item.get("template") or SiteTemplate(item.get("name", ""))
            if candidate.name == template.name:
                self.template_market_table.selectRow(row)
                break
        self.latest_market_recommendations = recommendations
        self.template_market_recommend_label.setText(
            f"模板市场推荐：{template.name}｜{top.get('category', '')}｜{use_case_name}｜评分 {top.get('score', 0)}"
        )
        self.append_ai_output(f"模板市场已自动推荐：{template.name}。{top.get('reason', '')}")
        return True

    def default_prompt_for_scene(self, preset):
        prompt_map = {
            "ecommerce": "抓取商品标题、价格、库存/规格、详情、图片和详情页链接",
            "article": "抓取文章标题、发布时间、作者/来源、正文和相关链接",
            "jobs": "抓取职位名称、薪资、公司、地点、岗位描述和详情链接",
            "company": "抓取公司名称、联系人、电话/邮箱、简介、官网和详情链接",
            "forum": "抓取帖子标题、作者、发布时间、正文、评论/互动信息和图片",
            "gallery": "抓取标题、图片地址、图片说明和详情页链接",
            "real_estate": "抓取房源标题、价格、面积/户型、位置、经纪人、详情和图片",
            "local_service": "抓取服务名称、价格/费用、联系人、电话/邮箱、服务介绍和地址",
        }
        return prompt_map.get(preset.template_type, "抓取当前页面的主要表格字段、图片、链接和正文")

    def run_wizard_preview(self, plan, html):
        if not isinstance(plan, dict) or not html:
            return False
        url = plan.get("url") or self.first_target_url()
        template_data = plan.get("template", {}) or {}
        rules = [
            FieldRule.from_dict(item)
            for item in template_data.get("field_rules", []) or []
            if isinstance(item, dict) and str(item.get("name", "")).strip()
        ]
        if not url or not rules:
            return False
        try:
            template = SiteTemplate(
                template_data.get("name") or "向导预采模板",
                field_rules=rules,
                next_page_selector=template_data.get("next_page_selector", ""),
            )
            record = UniversalExtractor(template).extract(html, url)
        except Exception as exc:
            self.append_ai_output(f"向导预采评分失败：{exc}")
            return False
        self.latest_preview_url = url
        self.latest_preview_html = html
        self.latest_preview_rules = rules
        self.show_preview_record(record, rules)
        self.append_ai_output(f"向导已自动预采 1 页并完成字段质量评分：{url}")
        return True

    def scan_subpage_links_for_current_url(self):
        url = self.first_target_url()
        if not url:
            QMessageBox.information(self, "提示", "请先输入网址。")
            return
        try:
            links = UniversalCollector(logger=self.append_ai_output).scan_subpage_links(
                url,
                use_browser=self.use_browser_checkbox.isChecked(),
                scroll_times=self.scroll_times_input.value(),
                keep_login_state=self.keep_login_checkbox.isChecked(),
                limit=120,
            )
        except Exception as exc:
            QMessageBox.warning(self, "扫描失败", str(exc))
            self.append_ai_output(f"扫描子页面失败：{exc}")
            return
        self.show_subpage_link_candidates(links)
        selected_count = len(self.selected_urls_from_subpage_table())
        self.append_ai_output(f"已扫描 {len(links)} 个候选链接，默认选中 {selected_count} 个同站详情候选。")

    def show_subpage_link_candidates(self, links):
        self.subpage_link_table.setRowCount(0)
        for link in links:
            row = self.subpage_link_table.rowCount()
            self.subpage_link_table.insertRow(row)
            checked = QTableWidgetItem()
            checked.setCheckState(Qt.CheckState.Checked if link.get("selected") else Qt.CheckState.Unchecked)
            self.subpage_link_table.setItem(row, 0, checked)
            values = [
                link.get("type", ""),
                link.get("text", ""),
                link.get("url", ""),
                link.get("reason", ""),
                link.get("score", ""),
            ]
            for offset, value in enumerate(values, start=1):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                if offset in (1, 4, 5):
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.subpage_link_table.setItem(row, offset, item)

    def selected_urls_from_subpage_table(self):
        urls = []
        for row in range(self.subpage_link_table.rowCount()):
            enabled = self.subpage_link_table.item(row, 0)
            if enabled and enabled.checkState() != Qt.CheckState.Checked:
                continue
            url_item = self.subpage_link_table.item(row, 3)
            url = normalize_url(url_item.text() if url_item else "")
            if url and url not in urls:
                urls.append(url)
        return urls

    def apply_selected_subpage_links(self):
        urls = self.selected_urls_from_subpage_table()
        self.selected_subpage_urls = urls
        self.subpage_limit_input.setValue(min(max(len(urls), 0), self.subpage_limit_input.maximum()))
        self.subpage_checkbox.setChecked(bool(urls))
        if urls:
            self.append_ai_output(f"已应用 {len(urls)} 个子页面。开始采集时会优先深抓这些链接。")
        else:
            self.append_ai_output("已清空手动选择的子页面链接，采集将按原设置自动判断。")

    def normalize_preview_value(self, value):
        if value is None:
            return ""
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return str(value).strip()

    def analyze_preview_quality(self, rules, preview_values):
        issues = []
        seen_values = {}
        seen_selectors = {}
        for rule in rules:
            raw_value = preview_values.get(rule.name, "")
            value = self.normalize_preview_value(raw_value)
            status = "正常"
            problem = ""
            advice = "可以正式采集"
            score = 100
            if not value:
                status = "需处理"
                problem = "空值"
                advice = "检查 CSS 选择器是否匹配页面，或换一个字段"
                score = 20
            elif value in seen_values and len(value) > 0:
                status = "需确认"
                problem = f"与「{seen_values[value]}」值重复"
                advice = "可能两个字段抓到了同一块内容，建议修改其中一个选择器"
                score = 65
            elif rule.selector in seen_selectors:
                status = "需确认"
                problem = f"与「{seen_selectors[rule.selector]}」选择器重复"
                advice = "同一个选择器用于多个字段，确认是否符合预期"
                score = 70
            elif len(value) > 5000:
                status = "需确认"
                problem = "内容过长"
                advice = "可能抓到了整页正文，建议缩小选择器范围"
                score = 75
            seen_values.setdefault(value, rule.name)
            seen_selectors.setdefault(rule.selector, rule.name)
            issues.append(
                {
                    "status": status,
                    "score": score,
                    "field": rule.name,
                    "problem": problem or "无",
                    "advice": advice,
                    "selector": rule.selector,
                }
            )
        return issues

    def quality_summary(self, issues):
        issues = issues or []
        if not issues:
            return {"score": 0, "need_fix": 0, "need_confirm": 0, "ok": 0, "summary": "字段质量评分：等待预采"}
        scores = [int(issue.get("score") or 0) for issue in issues]
        need_fix = sum(1 for issue in issues if issue.get("status") == "需处理")
        need_confirm = sum(1 for issue in issues if issue.get("status") == "需确认")
        ok_count = sum(1 for issue in issues if issue.get("status") == "正常")
        avg_score = round(sum(scores) / max(1, len(scores)))
        if need_fix:
            level = "需要修复"
        elif need_confirm:
            level = "建议确认"
        else:
            level = "可以采集"
        return {
            "score": avg_score,
            "need_fix": need_fix,
            "need_confirm": need_confirm,
            "ok": ok_count,
            "summary": f"字段质量评分：{avg_score}/100，{level}；正常 {ok_count}，需确认 {need_confirm}，需处理 {need_fix}",
        }

    def fill_quality_table(self, issues):
        self.ai_quality_table.setRowCount(0)
        summary = self.quality_summary(issues)
        if hasattr(self, "ai_quality_score_label"):
            self.ai_quality_score_label.setText(summary.get("summary", "字段质量评分：等待预采"))
        for issue in issues:
            row = self.ai_quality_table.rowCount()
            self.ai_quality_table.insertRow(row)
            values = [
                issue.get("status", ""),
                issue.get("score", ""),
                issue.get("field", ""),
                issue.get("problem", ""),
                issue.get("advice", ""),
                issue.get("selector", ""),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                if column == 0 and value == "需处理":
                    item.setBackground(Qt.GlobalColor.red)
                elif column == 0 and value == "需确认":
                    item.setBackground(Qt.GlobalColor.yellow)
                self.ai_quality_table.setItem(row, column, item)

    def result_quality_fields(self):
        base_fields = [
            ("标题", "title"),
            ("价格", "price"),
            ("时间", "published_time"),
            ("作者", "author"),
            ("正文", "body"),
            ("图片", "images"),
            ("链接", "links"),
            ("表格", "tables"),
            ("错误", "error"),
        ]
        custom_names = []
        for rule in self.collect_field_rules_from_table():
            if rule.name not in [name for name, _key in base_fields] and rule.name not in custom_names:
                custom_names.append(rule.name)
        return base_fields + [(name, name) for name in custom_names]

    def record_quality_value(self, record, key):
        if key in record:
            return record.get(key, "")
        body = record.get("body", "")
        marker = "自定义字段："
        if marker in body:
            try:
                custom_values = json.loads(body.split(marker, 1)[1].strip())
                return custom_values.get(key, "")
            except Exception:
                return ""
        return ""

    def analyze_result_quality(self, records=None):
        records = list(records if records is not None else self.records)
        if not records:
            return []
        total = len(records)
        issues = []
        for field_name, key in self.result_quality_fields():
            values = [self.normalize_preview_value(self.record_quality_value(record, key)) for record in records]
            empty_count = sum(1 for value in values if not value or value in {"[]", "{}"})
            non_empty = [value for value in values if value and value not in {"[]", "{}"}]
            duplicate_count = max(0, len(non_empty) - len(set(non_empty)))
            long_count = sum(1 for value in non_empty if len(value) > 5000)
            empty_rate = empty_count / max(1, total)
            duplicate_rate = duplicate_count / max(1, len(non_empty))
            score = 100
            problems = []
            advice = "可以继续使用"
            status = "正常"
            if key == "error" and non_empty:
                status = "需处理"
                score = 25
                problems.append(f"存在 {len(non_empty)} 条错误")
                advice = "查看错误列，必要时放慢采集或切换真实浏览器模式"
            elif empty_rate >= 0.8:
                status = "需处理"
                score = 25
                problems.append(f"空值率 {round(empty_rate * 100)}%")
                advice = "字段可能没有抓到，建议点 AI 修复问题列或调整选择器"
            elif empty_rate >= 0.4:
                status = "需确认"
                score = 60
                problems.append(f"空值率 {round(empty_rate * 100)}%")
                advice = "部分页面可能缺字段，建议抽查结果或增加子页面抓取"
            if key != "error" and duplicate_rate >= 0.6 and len(non_empty) >= 3:
                status = "需确认" if status == "正常" else status
                score = min(score, 65)
                problems.append(f"重复率 {round(duplicate_rate * 100)}%")
                advice = "可能抓到了同一块内容，建议检查选择器是否过宽"
            if long_count:
                status = "需确认" if status == "正常" else status
                score = min(score, 70)
                problems.append(f"{long_count} 条内容过长")
                advice = "可能抓到整页正文，建议缩小字段范围"
            issues.append(
                {
                    "status": status,
                    "score": score,
                    "field": field_name,
                    "empty": f"{empty_count}/{total}",
                    "duplicate": f"{duplicate_count}/{max(1, len(non_empty))}",
                    "problem": "；".join(problems) if problems else "无",
                    "advice": advice,
                }
            )
        return issues

    def result_quality_summary(self, issues):
        issues = issues or []
        if not issues:
            return "采集结果质量：等待结果"
        scores = [int(issue.get("score") or 0) for issue in issues]
        need_fix = sum(1 for issue in issues if issue.get("status") == "需处理")
        need_confirm = sum(1 for issue in issues if issue.get("status") == "需确认")
        ok_count = sum(1 for issue in issues if issue.get("status") == "正常")
        avg_score = round(sum(scores) / max(1, len(scores)))
        if need_fix:
            level = "需要修复"
        elif need_confirm:
            level = "建议抽查"
        else:
            level = "质量正常"
        return f"采集结果质量：{avg_score}/100，{level}；正常 {ok_count}，需确认 {need_confirm}，需处理 {need_fix}"

    def fill_result_quality_table(self, issues=None):
        if not hasattr(self, "result_quality_table"):
            return
        issues = self.analyze_result_quality() if issues is None else issues
        self.result_quality_table.setRowCount(0)
        if hasattr(self, "result_quality_score_label"):
            self.result_quality_score_label.setText(self.result_quality_summary(issues))
        for issue in issues:
            row = self.result_quality_table.rowCount()
            self.result_quality_table.insertRow(row)
            values = [
                issue.get("status", ""),
                issue.get("score", ""),
                issue.get("field", ""),
                issue.get("empty", ""),
                issue.get("duplicate", ""),
                issue.get("problem", ""),
                issue.get("advice", ""),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                if column == 0 and value == "需处理":
                    item.setBackground(Qt.GlobalColor.red)
                elif column == 0 and value == "需确认":
                    item.setBackground(Qt.GlobalColor.yellow)
                self.result_quality_table.setItem(row, column, item)

    def repair_quality_report_summary(self, rows):
        rows = rows or []
        if not rows:
            return "AI 修复验证：等待修复"
        improved = sum(1 for row in rows if row.get("result") == "改善")
        worse = sum(1 for row in rows if row.get("result") == "变差")
        unchanged = len(rows) - improved - worse
        before_scores = [int(row.get("before_score") or 0) for row in rows]
        after_scores = [int(row.get("after_score") or 0) for row in rows]
        before_avg = round(sum(before_scores) / max(1, len(before_scores)))
        after_avg = round(sum(after_scores) / max(1, len(after_scores)))
        delta = after_avg - before_avg
        level = "已改善" if improved and not worse else ("需继续调整" if worse else "变化不明显")
        sample_count = max(int(row.get("sample_count") or 0) for row in rows)
        sample_text = f"；样本 {sample_count} 条" if sample_count else ""
        return f"AI 修复验证：{before_avg} -> {after_avg}，{level}；改善 {improved}，持平 {unchanged}，变差 {worse}，总变化 {delta:+d}{sample_text}"

    def build_repair_quality_report(self, before_issues, after_issues):
        before_by_field = {item.get("field", ""): item for item in before_issues or [] if item.get("field")}
        after_by_field = {item.get("field", ""): item for item in after_issues or [] if item.get("field")}
        fields = []
        for field in list(before_by_field.keys()) + list(after_by_field.keys()):
            if field and field not in fields:
                fields.append(field)
        rows = []
        status_rank = {"正常": 0, "需确认": 1, "需处理": 2}
        for field in fields:
            before = before_by_field.get(field, {})
            after = after_by_field.get(field, {})
            before_score = int(before.get("score") or 0)
            after_score = int(after.get("score") or 0)
            before_status = before.get("status", "未检测")
            after_status = after.get("status", "未检测")
            before_rank = status_rank.get(before_status, 3)
            after_rank = status_rank.get(after_status, 3)
            delta = after_score - before_score
            if after_rank < before_rank or delta >= 10:
                result = "改善"
            elif after_rank > before_rank or delta <= -10:
                result = "变差"
            else:
                result = "持平"
            before_problem = before.get("problem", "无")
            after_problem = after.get("problem", "无")
            if result == "改善":
                advice = "可以保留当前修复字段"
            elif result == "变差":
                advice = "建议撤回或继续让 AI 缩小选择器"
            else:
                advice = after.get("advice") or before.get("advice") or "建议抽查样本"
            rows.append(
                {
                    "field": field,
                    "sample_count": after.get("sample_count") or before.get("sample_count") or "",
                    "before_score": before_score,
                    "after_score": after_score,
                    "score_delta": delta,
                    "before_status": before_status,
                    "after_status": after_status,
                    "before_problem": before_problem,
                    "after_problem": after_problem,
                    "advice": advice,
                    "result": result,
                }
            )
        return rows

    def fill_repair_quality_report_table(self, rows=None):
        if not hasattr(self, "repair_quality_report_table"):
            return
        rows = [] if rows is None else list(rows)
        self.repair_quality_report_rows = rows
        self.repair_quality_report_table.setRowCount(0)
        if hasattr(self, "repair_quality_report_label"):
            self.repair_quality_report_label.setText(self.repair_quality_report_summary(rows))
        for report in rows:
            row = self.repair_quality_report_table.rowCount()
            self.repair_quality_report_table.insertRow(row)
            delta = int(report.get("score_delta") or 0)
            values = [
                report.get("field", ""),
                report.get("sample_count", ""),
                f"{report.get('before_score', 0)}/{report.get('before_status', '')}",
                f"{report.get('after_score', 0)}/{report.get('after_status', '')}",
                f"{delta:+d}",
                f"{report.get('before_status', '')} -> {report.get('after_status', '')}",
                f"{report.get('before_problem', '')} -> {report.get('after_problem', '')}",
                report.get("advice", ""),
                report.get("result", ""),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                if column == 8 and value == "改善":
                    item.setBackground(Qt.GlobalColor.green)
                elif column == 8 and value == "变差":
                    item.setBackground(Qt.GlobalColor.red)
                elif column == 8 and value == "持平":
                    item.setBackground(Qt.GlobalColor.yellow)
                self.repair_quality_report_table.setItem(row, column, item)

    def update_repair_quality_report(self, before_issues, after_issues):
        rows = self.build_repair_quality_report(before_issues, after_issues)
        self.fill_repair_quality_report_table(rows)
        if rows:
            self.append_ai_output(self.repair_quality_report_summary(rows))
            self.save_ai_repair_history(rows)
            self.prepare_secondary_repair_prompt(rows)
        return rows

    def ai_repair_history_entry(self, rows):
        rows = list(rows or [])
        improved = sum(1 for row in rows if row.get("result") == "改善")
        worse = sum(1 for row in rows if row.get("result") == "变差")
        unchanged = len(rows) - improved - worse
        deltas = [int(row.get("score_delta") or 0) for row in rows]
        sample_count = max([int(row.get("sample_count") or 0) for row in rows] or [0])
        failed_fields = [row.get("field", "") for row in rows if row.get("result") in ("持平", "变差")]
        provider = self.ai_provider_combo.currentData() if hasattr(self, "ai_provider_combo") else self.ai_settings.get("provider", "")
        provider_name = (AI_PROVIDER_PRESETS.get(provider, {}) or {}).get("name") or self.ai_settings.get("provider_name", provider)
        model = self.current_ai_model_text() if hasattr(self, "ai_model_combo") else self.ai_settings.get("model", "")
        return {
            "provider": provider,
            "provider_name": provider_name,
            "model": model,
            "sample_count": sample_count,
            "field_count": len(rows),
            "improved_count": improved,
            "unchanged_count": unchanged,
            "worse_count": worse,
            "avg_delta": round(sum(deltas) / max(1, len(deltas)), 1),
            "failed_fields": failed_fields,
            "field_rules": [rule.to_dict() for rule in self.collect_field_rules_from_table()],
            "report_rows": rows,
        }

    def save_ai_repair_history(self, rows):
        if not rows:
            return None
        entry = append_ai_repair_history(self.ai_repair_history_entry(rows))
        self.refresh_ai_repair_history()
        return entry

    def secondary_repair_issues_from_report(self, rows):
        rules_by_name = {rule.name: rule for rule in self.collect_field_rules_from_table()}
        issues = []
        for row in rows or []:
            if row.get("result") == "改善":
                continue
            field = row.get("field", "")
            if not field:
                continue
            rule = rules_by_name.get(field)
            issues.append(
                {
                    "status": "需处理" if row.get("result") == "变差" else "需确认",
                    "score": row.get("after_score", ""),
                    "field": field,
                    "problem": f"修复后仍未稳定：{row.get('after_problem', '')}",
                    "advice": row.get("advice", "继续缩小选择器或换更准确字段来源"),
                    "selector": rule.selector if rule else "",
                    "sample_count": row.get("sample_count", ""),
                    "score_delta": row.get("score_delta", ""),
                    "repair_result": row.get("result", ""),
                }
            )
        return issues

    def secondary_repair_prompt_text(self, issues):
        if not issues:
            return ""
        lines = [
            "请继续修复上一轮没有变好的字段，优先让多样本验证变为“改善”：",
        ]
        for issue in issues:
            selector = issue.get("selector") or "未填写"
            sample_count = issue.get("sample_count") or "未知"
            delta = issue.get("score_delta")
            lines.append(
                f"- {issue.get('field')}：{issue.get('repair_result')}，{issue.get('problem')}；"
                f"当前选择器：{selector}；样本数：{sample_count}；分数变化：{delta}"
            )
        lines.append("要求：不要删除已经改善的字段；只调整以上失败字段；返回完整 fields 数组。")
        return "\n".join(lines)

    def prepare_secondary_repair_prompt(self, report_rows):
        issues = self.secondary_repair_issues_from_report(report_rows)
        self.secondary_repair_issues = issues
        if not issues:
            return []
        prompt = self.secondary_repair_prompt_text(issues)
        if prompt:
            self.ai_prompt_input.setPlainText(prompt)
        self.append_ai_output(f"已准备二次 AI 修复提示：{len(issues)} 个字段仍需继续修。")
        return issues

    def repair_sample_sources(self, limit=3):
        sources = []
        seen = set()
        for record in list(self.records or []):
            url = normalize_url(record.get("url", ""))
            if not url or url in seen:
                continue
            seen.add(url)
            sources.append({"url": url, "html": ""})
            if len(sources) >= limit:
                return sources
        if self.latest_preview_url and self.latest_preview_html:
            sources.append({"url": self.latest_preview_url, "html": self.latest_preview_html})
        return sources[:limit]

    def verify_repaired_fields_on_samples(self, rules, limit=3):
        sources = self.repair_sample_sources(limit)
        if not sources:
            return []
        template = SiteTemplate("AI 修复多样本验证模板", field_rules=rules)
        extractor = UniversalExtractor(template)
        verified_records = []
        for source in sources:
            url = normalize_url(source.get("url", ""))
            html = source.get("html", "")
            if not url:
                continue
            if not html:
                if url == self.latest_preview_url and self.latest_preview_html:
                    html = self.latest_preview_html
                else:
                    try:
                        html = self.fetch_snapshot_html(url)
                    except Exception as exc:
                        verified_records.append({"url": url, "error": f"重采样失败：{exc}"})
                        continue
            try:
                verified_records.append(extractor.extract(html, url))
            except Exception as exc:
                verified_records.append({"url": url, "error": f"重采样抽取失败：{exc}"})
        return verified_records

    def analyze_repaired_sample_quality(self, records, fields):
        issues = self.analyze_result_quality(records)
        wanted = set(fields or [])
        result = []
        sample_count = len(records or [])
        for issue in issues:
            if wanted and issue.get("field") not in wanted:
                continue
            item = dict(issue)
            item["sample_count"] = sample_count
            result.append(item)
        return result

    def result_quality_issues_for_repair(self, issues=None):
        issues = issues if issues is not None else self.analyze_result_quality()
        repair_issues = []
        rules_by_name = {rule.name: rule for rule in self.collect_field_rules_from_table()}
        for issue in issues or []:
            if issue.get("status") not in ("需处理", "需确认"):
                continue
            field = issue.get("field", "")
            if field == "错误":
                continue
            rule = rules_by_name.get(field)
            repair_issues.append(
                {
                    "status": issue.get("status", ""),
                    "score": issue.get("score", ""),
                    "field": field,
                    "problem": issue.get("problem", ""),
                    "advice": issue.get("advice", ""),
                    "selector": rule.selector if rule else "",
                    "empty": issue.get("empty", ""),
                    "duplicate": issue.get("duplicate", ""),
                }
            )
        return repair_issues

    def ai_repair_from_result_quality(self):
        issues = self.result_quality_issues_for_repair()
        if not issues:
            QMessageBox.information(self, "提示", "当前采集结果质量没有可自动修复的字段问题。")
            return
        rules = self.collect_field_rules_from_table()
        if not rules:
            QMessageBox.information(self, "提示", "请先在模板库配置字段，或先让 AI 建议列。")
            return
        url = self.latest_preview_url or self.first_target_url()
        if not url and self.records:
            url = self.records[0].get("url", "")
        html = self.latest_preview_html
        if not url:
            QMessageBox.information(self, "提示", "没有可用于修复的样本网址。")
            return
        if not html:
            try:
                html = self.fetch_snapshot_html(url)
            except Exception as exc:
                QMessageBox.warning(self, "读取网页失败", str(exc))
                return
        self.latest_quality_issues = issues
        self.fill_quality_table(issues)
        self.latest_preview_url = url
        self.latest_preview_html = html
        self.latest_preview_rules = rules
        self.repair_quality_before_issues = [dict(issue) for issue in issues]
        self.fill_repair_quality_report_table([])
        self.auto_apply_repair_after_ai = True
        self.append_ai_output(f"已把采集结果质量问题转为 AI 修复任务：{len(issues)} 个字段。")
        self.run_ai_worker(
            "repair_fields",
            {
                "url": url,
                "html": html,
                "field_rules": [rule.to_dict() for rule in rules],
                "quality_issues": issues,
                "goal": self.ai_prompt_input.toPlainText().strip() or "根据采集结果质量总览修复空值、重复或过长字段",
            },
        )

    def ai_generate_task(self):
        prompt = self.ai_prompt_input.toPlainText().strip()
        if not prompt:
            QMessageBox.information(self, "提示", "请先描述要抓取什么。")
            return
        url = self.first_target_url()
        snapshot = {}
        if url:
            try:
                snapshot = page_snapshot_from_html(url, self.fetch_snapshot_html(url))
            except Exception as exc:
                self.append_ai_output(f"网页快照读取失败，仅按文字需求生成：{exc}")
        self.run_ai_worker("parse_task", {"prompt": prompt, "snapshot": snapshot})

    def ai_run_agent(self):
        url = self.first_target_url()
        if not url:
            QMessageBox.information(self, "提示", "请先输入网址。")
            return
        plan = self.latest_ai_result if isinstance(self.latest_ai_result, dict) else {}
        actions = plan.get("actions") if isinstance(plan, dict) else []
        if actions:
            self.show_ai_task_plan(plan)
            self.append_ai_output(f"将按预览计划执行 {len(actions)} 个 Agent 动作。")
        if not actions:
            actions = [
                {
                    "type": "extract",
                    "template_name": self.selected_template_name(),
                    "field_rules": [rule.to_dict() for rule in self.collect_field_rules_from_table()],
                }
            ]
        self.run_ai_worker(
            "agent",
            {
                "url": url,
                "actions": actions,
                "keep_login_state": self.keep_login_checkbox.isChecked(),
                "headless": True,
            },
        )

    def ai_transform_current_records(self):
        if not self.records:
            QMessageBox.information(self, "提示", "请先完成一次网页采集。")
            return
        instruction = self.ai_prompt_input.toPlainText().strip() or "整理成更适合表格分析的字段"
        self.run_ai_worker("transform_records", {"records": self.records, "instruction": instruction})

    def ai_extract_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 PDF / 图片 / 文本",
            os.getcwd(),
            "可提取文件 (*.pdf *.png *.jpg *.jpeg *.webp *.bmp *.txt *.csv);;所有文件 (*.*)",
        )
        if not file_path:
            return
        instruction = self.ai_prompt_input.toPlainText().strip()
        self.run_ai_worker("extract_file", {"file_path": file_path, "instruction": instruction})

    def extract_email_phone_current(self):
        records = self.records or self.database.recent_records(200)
        result = extract_emails_and_phones(records)
        self.show_ai_json(result)
        rows = [
            [
                item.get("content", ""),
                item.get("type", ""),
                item.get("source_title", ""),
                item.get("source_url", ""),
            ]
            for item in result.get("rows", [])
        ]
        self.fill_ai_table(["内容", "类型", "来源标题", "来源网址"], rows)
        self.append_ai_output(f"线索提取完成：邮箱 {len(result.get('emails', []))} 个，电话 {len(result.get('phones', []))} 个。")

    def download_current_images(self):
        records = self.records or self.database.recent_records(200)
        if not records:
            QMessageBox.information(self, "提示", "没有可下载图片的采集结果。")
            return
        target_dir = QFileDialog.getExistingDirectory(self, "选择图片保存目录", os.getcwd())
        if not target_dir:
            return
        if os.environ.get("UNIVERSAL_COLLECTOR_SELF_TEST") == "1":
            saved = download_images_from_records(records, target_dir, logger=self.append_ai_output)
            self.image_download_context = "ai"
            self.on_image_download_result(saved, target_dir)
            self.image_download_context = ""
            return
        self.start_image_download(records, target_dir, context="ai")

    def show_schedule_hint(self):
        minutes, ok = self.simple_int_dialog("计划采集", "每隔多少分钟自动采集一次当前任务？", 30, 1, 1440)
        if not ok:
            return
        self.add_schedule_from_current_config(minutes=minutes)

    def save_schedule_state(self):
        self.schedules = save_schedules(self.schedules)
        if hasattr(self, "schedule_table"):
            self.fill_schedule_table()
        self.refresh_overview()

    def fill_schedule_table(self):
        if not hasattr(self, "schedule_table"):
            return
        selected_id = ""
        selected_index = self.selected_schedule_index()
        if selected_index >= 0 and selected_index < len(self.schedules):
            selected_id = self.schedules[selected_index].get("id", "")
        self.schedule_table.setRowCount(0)
        for source in self.schedules or []:
            row = self.schedule_table.rowCount()
            self.schedule_table.insertRow(row)
            config = source.get("config") or {}
            urls = config.get("urls") or []
            values = [
                "启用" if source.get("enabled") else "停用",
                source.get("name", ""),
                f"{source.get('interval_minutes', 0)} 分钟",
                source.get("next_run_at", ""),
                source.get("last_run_at", ""),
                source.get("run_count", 0),
                source.get("last_status", ""),
                len(urls),
                source.get("id", ""),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.schedule_table.setItem(row, column, item)
            if selected_id and source.get("id") == selected_id:
                self.schedule_table.selectRow(row)

    def selected_schedule_index(self):
        if not hasattr(self, "schedule_table"):
            return -1
        selected = self.schedule_table.selectionModel().selectedRows()
        if not selected:
            return -1
        schedule_id_item = self.schedule_table.item(selected[0].row(), 8)
        schedule_id = schedule_id_item.text() if schedule_id_item else ""
        for index, source in enumerate(self.schedules or []):
            if source.get("id") == schedule_id:
                return index
        return -1

    def add_schedule_from_current_config(self, minutes=None):
        urls = self.urls_from_input()
        if not urls:
            QMessageBox.information(self, "提示", "请先输入至少一个网址。")
            return None
        if minutes is None:
            minutes, ok = self.simple_int_dialog("新增计划采集", "每隔多少分钟自动采集一次当前任务？", 30, 1, 1440)
            if not ok:
                return None
        config = self.current_run_config(urls)
        name = f"{self.selected_template_name()}｜{len(urls)} 个网址"
        item = new_schedule_item(name, int(minutes or 30), config)
        self.schedules.append(item)
        self.save_schedule_state()
        self.show_history_section("计划采集")
        self.append_ai_output(f"已新增计划采集：{item['name']}，每 {item['interval_minutes']} 分钟运行一次。")
        return item

    def toggle_selected_schedule(self):
        index = self.selected_schedule_index()
        if index < 0:
            QMessageBox.information(self, "提示", "请先选择一个计划采集任务。")
            return
        self.schedules[index]["enabled"] = not bool(self.schedules[index].get("enabled"))
        self.schedules[index]["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        state = "启用" if self.schedules[index]["enabled"] else "停用"
        self.save_schedule_state()
        self.append_ai_output(f"计划采集已{state}：{self.schedules[index].get('name', '')}")

    def delete_selected_schedule(self):
        index = self.selected_schedule_index()
        if index < 0:
            QMessageBox.information(self, "提示", "请先选择一个计划采集任务。")
            return
        removed = self.schedules.pop(index)
        self.save_schedule_state()
        self.append_ai_output(f"已删除计划采集：{removed.get('name', '')}")

    def apply_schedule_config_to_ui(self, schedule):
        config = (schedule or {}).get("config") or {}
        urls = config.get("urls") or []
        if urls:
            self.url_input.setPlainText("\n".join(urls))
            self.ai_url_input.setText(urls[0])
            self.pick_url_input.setText(urls[0])
        template_name = config.get("template_name", "")
        if template_name:
            index = self.template_combo.findText(template_name)
            if index >= 0:
                self.template_combo.setCurrentIndex(index)
        self.use_browser_checkbox.setChecked(bool(config.get("use_browser", True)))
        self.scroll_times_input.setValue(int(config.get("scroll_times", DEFAULT_SCROLL_TIMES) or 0))
        self.page_limit_input.setValue(int(config.get("page_limit", DEFAULT_PAGE_LIMIT) or 1))
        self.delay_input.setValue(int(config.get("delay_seconds", 1) or 0))
        self.keep_login_checkbox.setChecked(bool(config.get("keep_login_state", False)))
        self.skip_unchanged_checkbox.setChecked(bool(config.get("skip_unchanged", True)))
        self.subpage_checkbox.setChecked(bool(config.get("scrape_subpages", False)))
        self.subpage_limit_input.setValue(int(config.get("subpage_limit", 0) or 0))
        self.selected_subpage_urls = list(config.get("selected_subpage_urls") or [])

    def mark_schedule_run(self, schedule_id, status, message="", count_run=False):
        for source in self.schedules:
            if source.get("id") != schedule_id:
                continue
            source["last_run_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            source["next_run_at"] = schedule_next_run_text(source.get("interval_minutes", 30))
            if count_run:
                source["run_count"] = int(source.get("run_count") or 0) + 1
            source["last_status"] = status
            source["last_message"] = message
            source["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            break
        self.save_schedule_state()

    def run_schedule(self, schedule):
        schedule_id = (schedule or {}).get("id", "")
        if self.worker:
            self.mark_schedule_run(schedule_id, "已跳过", "已有采集任务正在运行")
            self.append_log("已有采集任务正在运行，本次计划采集已跳过。")
            return False
        self.apply_schedule_config_to_ui(schedule)
        self.active_schedule_id = schedule_id
        self.mark_schedule_run(schedule_id, "已触发", "计划采集已启动")
        self.start_collecting()
        return True

    def run_selected_schedule_now(self):
        index = self.selected_schedule_index()
        if index < 0:
            QMessageBox.information(self, "提示", "请先选择一个计划采集任务。")
            return
        self.run_schedule(dict(self.schedules[index]))

    def start_schedule_tick(self):
        if self.schedule_tick_timer:
            self.schedule_tick_timer.stop()
        self.schedule_tick_timer = QTimer(self)
        self.schedule_tick_timer.timeout.connect(self.check_due_schedules)
        self.schedule_tick_timer.start(60 * 1000)

    def check_due_schedules(self):
        if self.worker:
            return
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        for source in list(self.schedules or []):
            if not source.get("enabled"):
                continue
            next_run = source.get("next_run_at") or ""
            if not next_run or next_run <= now:
                self.run_schedule(dict(source))
                break

    def simple_int_dialog(self, title, label, value, minimum, maximum):
        from PyQt6.QtWidgets import QInputDialog

        return QInputDialog.getInt(self, title, label, value, minimum, maximum)

    def on_ai_result(self, action, result):
        if isinstance(result, dict) and result.get("error"):
            if action == "simple_suggest_fields":
                self.simple_ai_suggest_pending = False
                self.simple_ai_field_rules = []
                self.refresh_simple_field_table()
                self.append_ai_output(f"普通首页 AI 建议列失败，已改用本地规则：{result['error']}")
                if hasattr(self, "simple_status_label") and not self.worker:
                    self.simple_status_label.setText("AI 建议列暂不可用，已用本地规则整理")
                return
            if action == "test_api":
                self.update_current_ai_key_status("失败", result["error"])
            self.append_ai_output(f"AI 任务失败：{result['error']}")
            QMessageBox.warning(self, "AI 任务失败", result["error"])
            return
        self.latest_ai_result = result
        if isinstance(result, dict) and result.get("_auto_switched_key"):
            self.apply_auto_switched_ai_key(result.get("_auto_switched_key", ""))
        self.show_ai_json(result)
        if action == "test_api":
            self.update_current_ai_key_status("可用", "")
            self.append_ai_output("API Key 测试成功，已标记为可用。")
            self.refresh_ai_provider_overview()
        elif action == "diagnose_api":
            self.fill_ai_diagnosis_table(result.get("checks", []) if isinstance(result, dict) else [])
            self.refresh_api_health_summary(result if isinstance(result, dict) else None)
            self.append_ai_output(result.get("summary", "配置诊断完成。") if isinstance(result, dict) else "配置诊断完成。")
            self.refresh_ai_provider_overview()
        elif action == "fetch_models":
            fetched_models = self.unique_models([str(model) for model in result])
            current_model = self.current_ai_model_text()
            self.ai_model_cache = self.unique_models(fetched_models + self.ai_model_cache)
            self.refresh_ai_model_combo(current_model or (self.ai_model_cache[0] if self.ai_model_cache else ""))
            current_settings = self.collect_ai_settings_from_ui()
            current_settings["models_updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            current_settings["models_refresh_error"] = ""
            self.ai_settings = save_ai_settings(current_settings)
            self.append_ai_output(f"已拉取并缓存 {len(fetched_models)} 个模型，当前厂商下次打开会保留。")
            self.refresh_ai_provider_overview()
        elif action == "refresh_provider_models":
            result_settings = result.get("settings", {}) if isinstance(result, dict) else {}
            if isinstance(result_settings, dict):
                self.ai_settings = save_ai_settings(result_settings)
                current_provider = self.ai_provider_combo.currentData() or self.ai_settings.get("provider", "openai")
                provider_settings = (self.ai_settings.get("providers") or {}).get(current_provider, {})
                if provider_settings:
                    self.ai_model_cache = self.unique_models(
                        (provider_settings.get("model_cache") or []) + (provider_settings.get("models") or [])
                    )
                    self.refresh_ai_model_combo(provider_settings.get("model", self.current_ai_model_text()))
            rows = result.get("results", []) if isinstance(result, dict) else []
            success_count = sum(1 for item in rows if item.get("status") == "成功")
            skipped_count = sum(1 for item in rows if item.get("status") == "跳过")
            failed_count = sum(1 for item in rows if item.get("status") == "失败")
            self.fill_ai_diagnosis_table(
                [
                    {
                        "level": "正常" if item.get("status") == "成功" else "需确认",
                        "item": item.get("provider_name", item.get("provider", "")),
                        "status": f"{item.get('status')}｜{item.get('model_count', 0)} 个",
                        "advice": item.get("message", ""),
                    }
                    for item in rows
                ]
            )
            self.append_ai_output(f"批量刷新模型完成：成功 {success_count}，跳过 {skipped_count}，失败 {failed_count}。")
            self.refresh_api_health_summary()
            self.refresh_ai_provider_overview()
        elif action == "test_provider_connectivity":
            result_settings = result.get("settings", {}) if isinstance(result, dict) else {}
            if isinstance(result_settings, dict):
                self.ai_settings = save_ai_settings(result_settings)
                current_provider = self.ai_provider_combo.currentData() or self.ai_settings.get("provider", "openai")
                provider_settings = (self.ai_settings.get("providers") or {}).get(current_provider, {})
                if provider_settings:
                    self.ai_key_entries = normalize_api_key_entries(
                        provider_settings.get("api_keys"),
                        provider_settings.get("api_key", ""),
                        provider_settings.get("active_api_key_name", ""),
                    )
                    self.refresh_ai_key_combo(provider_settings.get("active_api_key_name", ""))
            rows = result.get("results", []) if isinstance(result, dict) else []
            success_count = sum(1 for item in rows if item.get("status") == "成功")
            skipped_count = sum(1 for item in rows if item.get("status") == "跳过")
            failed_count = sum(1 for item in rows if item.get("status") == "失败")
            self.fill_ai_diagnosis_table(
                [
                    {
                        "level": "正常" if item.get("status") == "成功" else "需确认",
                        "item": item.get("provider_name", item.get("provider", "")),
                        "status": f"{item.get('status')}｜{item.get('model', '')}",
                        "advice": item.get("message", ""),
                    }
                    for item in rows
                ]
            )
            self.append_ai_output(f"一键测试模型完成：成功 {success_count}，跳过 {skipped_count}，失败 {failed_count}。")
            self.refresh_api_health_summary()
            self.refresh_ai_provider_overview()
        elif action == "suggest_fields":
            self.apply_ai_fields(result)
        elif action == "simple_suggest_fields":
            self.apply_simple_ai_fields(result)
        elif action == "repair_fields":
            self.apply_repaired_fields(result)
        elif action == "parse_task":
            self.apply_ai_task(result)
        elif action == "transform_records":
            self.apply_ai_table_result(result)
        elif action == "extract_file":
            self.apply_ai_table_result(result)
            if hasattr(self, "simple_status_label"):
                if isinstance(result, dict) and result.get("error"):
                    self.simple_status_label.setText(f"文件提取失败：{result.get('error')}")
                    self.set_simple_flow_step("输入")
                else:
                    row_count = len(result.get("rows", []) or []) if isinstance(result, dict) else 0
                    self.simple_status_label.setText(f"文件已转成表格，共 {row_count} 行，可以直接自动保存")
                    self.simple_progress_label.setText("后台：文件表格已生成")
                    self.set_simple_flow_step("导出")
        elif action == "agent":
            records = result.get("records", []) if isinstance(result, dict) else []
            for record in records:
                self.records.append(record)
                self.add_record_to_table(self.result_table, record, "current", len(self.records) - 1)
            self.append_ai_output(f"Agent 已提取 {len(records)} 条记录。")

    def fill_ai_diagnosis_table(self, checks):
        self.ai_diagnosis_table.setRowCount(0)
        for check in checks or []:
            if not isinstance(check, dict):
                continue
            row = self.ai_diagnosis_table.rowCount()
            self.ai_diagnosis_table.insertRow(row)
            values = [
                check.get("level", ""),
                check.get("item", ""),
                check.get("status", ""),
                check.get("advice", ""),
            ]
            for column, value in enumerate(values):
                self.ai_diagnosis_table.setItem(row, column, QTableWidgetItem(str(value)))

    def apply_auto_switched_ai_key(self, key_name):
        entry = next((item for item in getattr(self, "ai_key_entries", []) if item.get("name") == key_name), None)
        if not entry:
            return
        self.ai_key_name_input.setText(entry.get("name", ""))
        self.ai_key_input.setText(entry.get("key", ""))
        self.refresh_ai_key_combo(entry.get("name", ""))
        self.ai_settings = save_ai_settings(self.collect_ai_settings_from_ui())
        self.append_ai_output(f"已同步当前 Key 为自动重试成功的 Key：{entry.get('name')}（{mask_api_key(entry.get('key'))}）")

    def show_ai_json(self, result):
        self.ai_output.appendPlainText(json.dumps(result, ensure_ascii=False))

    def apply_ai_fields(self, result):
        fields = result.get("fields") if isinstance(result, dict) else result
        if not isinstance(fields, list):
            self.append_ai_output("AI 没有返回 fields 数组。")
            return
        self.show_ai_suggested_fields(fields)
        self.append_ai_output(f"AI 已建议 {self.ai_suggest_table.rowCount()} 个字段，请勾选后应用到模板。")

    def apply_repaired_fields(self, result):
        fields = result.get("fields") if isinstance(result, dict) else result
        if not isinstance(fields, list):
            self.append_ai_output("AI 没有返回修复后的 fields 数组。")
            return
        self.show_ai_suggested_fields(fields)
        self.latest_quality_issues = []
        self.fill_quality_table([])
        if self.auto_apply_repair_after_ai:
            self.auto_apply_repair_after_ai = False
            if self.apply_repaired_fields_to_template(auto_preview=True):
                self.append_ai_output(f"AI 已修复并自动应用 {self.ai_suggest_table.rowCount()} 个字段，已重新预采评分。")
                return
        self.append_ai_output(f"AI 已回填 {self.ai_suggest_table.rowCount()} 个修复后字段，可点“应用 AI 修复到模板”后重新预采一页确认。")

    def apply_repaired_fields_to_template(self, auto_preview=False):
        rules = self.suggested_field_rules_from_table()
        if not rules:
            QMessageBox.information(self, "提示", "请先让 AI 修复问题列，或在建议列表里保留至少一个字段。")
            return False
        self.field_table.setRowCount(0)
        for rule in rules:
            self.add_field_row(rule)
        self.latest_preview_rules = rules
        preview_done = False
        if auto_preview:
            preview_done = self.preview_with_rules(rules, self.latest_preview_url or self.first_target_url(), self.latest_preview_html)
            if preview_done and self.repair_quality_before_issues:
                repair_fields = [issue.get("field", "") for issue in self.repair_quality_before_issues if issue.get("field")]
                sample_records = self.verify_repaired_fields_on_samples(rules, limit=3)
                self.repair_quality_sample_records = sample_records
                sample_issues = self.analyze_repaired_sample_quality(sample_records, repair_fields) if sample_records else []
                if sample_issues:
                    self.update_repair_quality_report(self.repair_quality_before_issues, sample_issues)
                    self.append_ai_output(f"已用 {len(sample_records)} 条样本重采验证 AI 修复效果。")
                else:
                    self.update_repair_quality_report(self.repair_quality_before_issues, self.latest_quality_issues)
                    self.append_ai_output("未找到可重采样本，已用当前预采页验证 AI 修复效果。")
        if not auto_preview:
            self.show_main_tab("模板库")
        message = f"已将 {len(rules)} 个修复字段应用到模板编辑器。"
        if preview_done:
            message += "已自动重新预采并刷新质量评分。"
        else:
            message += "请重新预采确认质量评分。"
        self.append_ai_output(message)
        return True

    def preview_with_rules(self, rules, url="", html=""):
        url = normalize_url(url) or self.first_target_url()
        if not url or not html or not rules:
            return False
        try:
            template = SiteTemplate("AI 修复预采模板", field_rules=rules)
            record = UniversalExtractor(template).extract(html, url)
        except Exception as exc:
            self.append_ai_output(f"自动重新预采失败：{exc}")
            return False
        self.latest_preview_url = url
        self.latest_preview_html = html
        self.latest_preview_rules = rules
        self.show_preview_record(record, rules)
        return True

    def show_ai_suggested_fields(self, fields):
        self.ai_suggest_table.setRowCount(0)
        for field in fields:
            if not isinstance(field, dict):
                continue
            row = self.ai_suggest_table.rowCount()
            self.ai_suggest_table.insertRow(row)
            enable_item = QTableWidgetItem()
            enable_item.setCheckState(Qt.CheckState.Checked)
            self.ai_suggest_table.setItem(row, 0, enable_item)
            self.ai_suggest_table.setItem(row, 1, QTableWidgetItem(str(field.get("name", "自定义字段"))))
            self.ai_suggest_table.setItem(row, 2, QTableWidgetItem(str(field.get("selector", ""))))
            attr_combo = QComboBox()
            for attr in ("text", "href", "src", "content", "data-src"):
                attr_combo.addItem(attr)
            attr_value = str(field.get("attr", "text") or "text")
            attr_index = attr_combo.findText(attr_value)
            attr_combo.setCurrentIndex(max(0, attr_index))
            self.ai_suggest_table.setCellWidget(row, 3, attr_combo)
            multi_item = QTableWidgetItem()
            multi_item.setCheckState(Qt.CheckState.Checked if field.get("multiple", False) else Qt.CheckState.Unchecked)
            self.ai_suggest_table.setItem(row, 4, multi_item)
            reason_item = QTableWidgetItem(str(field.get("reason", "")))
            reason_item.setFlags(reason_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.ai_suggest_table.setItem(row, 5, reason_item)

    def suggested_field_rules_from_table(self):
        rules = []
        for row in range(self.ai_suggest_table.rowCount()):
            enabled = self.ai_suggest_table.item(row, 0)
            if enabled and enabled.checkState() != Qt.CheckState.Checked:
                continue
            name_item = self.ai_suggest_table.item(row, 1)
            selector_item = self.ai_suggest_table.item(row, 2)
            attr_widget = self.ai_suggest_table.cellWidget(row, 3)
            multi_item = self.ai_suggest_table.item(row, 4)
            name = name_item.text().strip() if name_item else ""
            selector = selector_item.text().strip() if selector_item else ""
            if not name or not selector:
                continue
            attr = attr_widget.currentText() if isinstance(attr_widget, QComboBox) else "text"
            multiple = bool(multi_item and multi_item.checkState() == Qt.CheckState.Checked)
            rules.append(FieldRule(name, selector, attr, multiple))
        return rules

    def apply_checked_ai_fields_to_template(self):
        rules = self.suggested_field_rules_from_table()
        if not rules:
            QMessageBox.information(self, "提示", "请至少保留一个启用的建议列。")
            return
        self.field_table.setRowCount(0)
        for rule in rules:
            self.add_field_row(rule)
        self.show_main_tab("模板库")
        self.append_ai_output(f"已把 {len(rules)} 个已确认建议列应用到模板编辑器。")

    def select_all_ai_suggested_fields(self):
        for row in range(self.ai_suggest_table.rowCount()):
            item = self.ai_suggest_table.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Checked)

    def clear_ai_suggested_fields(self):
        self.ai_suggest_table.setRowCount(0)

    def apply_ai_task(self, result):
        self.show_ai_task_plan(result)
        self.append_ai_output("AI 采集任务计划已生成，请先检查计划预览，再应用或执行。")

    def show_ai_task_plan(self, result):
        self.ai_task_plan_table.setRowCount(0)
        if not isinstance(result, dict):
            self.ai_task_plan_label.setText("自然语言任务计划：AI 未返回可识别计划")
            return
        template_data = result.get("template", {}) or {}
        options = result.get("options", {}) or {}
        actions = result.get("actions", []) or []
        field_rules = template_data.get("field_rules", []) if isinstance(template_data, dict) else []
        title = template_data.get("name") if isinstance(template_data, dict) else ""
        page_kind = result.get("page_kind", "") if isinstance(result, dict) else ""
        kind_text = f" | {page_kind}" if page_kind else ""
        self.ai_task_plan_label.setText(
            f"自然语言任务计划：{title or '未命名任务'}{kind_text} | 字段 {len(field_rules)} 个 | 动作 {len(actions)} 个"
        )
        if template_data:
            self.add_ai_task_plan_row(
                "模板",
                template_data.get("name") or "AI 生成模板",
                json.dumps(
                    {
                        "domain": template_data.get("domain", ""),
                        "template_type": template_data.get("template_type", ""),
                        "next_page_selector": template_data.get("next_page_selector", ""),
                    },
                    ensure_ascii=False,
                ),
                "生成或更新采集模板",
            )
            for field in field_rules:
                if isinstance(field, dict):
                    self.add_ai_task_plan_row(
                        "字段",
                        field.get("name", "字段"),
                        f"{field.get('selector', '')} | {field.get('attr', 'text')}",
                        field.get("reason", ""),
                    )
        if options:
            self.add_ai_task_plan_row(
                "选项",
                "采集参数",
                json.dumps(options, ensure_ascii=False),
                "应用到批量采集配置",
            )
        signals = result.get("signals", {}) if isinstance(result, dict) else {}
        recommendations = result.get("recommendations", []) if isinstance(result, dict) else []
        if signals:
            self.add_ai_task_plan_row(
                "诊断",
                result.get("page_kind", "页面结构"),
                json.dumps(signals, ensure_ascii=False),
                f"推荐模板：{result.get('template_name', '')}；置信度：{result.get('confidence', '')}%",
            )
        for item in recommendations:
            self.add_ai_task_plan_row("建议", "下一步", str(item), "任务向导")
        for index, action in enumerate(actions, start=1):
            if not isinstance(action, dict):
                continue
            action_type = action.get("type", "action")
            self.add_ai_task_plan_row(
                "动作",
                f"{index}. {action_type}",
                json.dumps(action, ensure_ascii=False),
                "网页自动化 Agent 将按顺序执行",
            )

    def add_ai_task_plan_row(self, item_type, name, params, note):
        row = self.ai_task_plan_table.rowCount()
        self.ai_task_plan_table.insertRow(row)
        for column, value in enumerate((item_type, name, params, note)):
            item = QTableWidgetItem(str(value))
            item.setToolTip(str(value))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.ai_task_plan_table.setItem(row, column, item)

    def apply_current_ai_task_plan(self):
        result = self.latest_ai_result if isinstance(self.latest_ai_result, dict) else {}
        if not result:
            QMessageBox.information(self, "提示", "请先生成自然语言采集任务。")
            return False
        template_data = result.get("template", {}) if isinstance(result, dict) else {}
        if template_data:
            target_template_name = template_data.get("name") or "AI 生成模板"
            template = SiteTemplate(
                name=target_template_name,
                domain=template_data.get("domain") or url_domain(self.first_target_url()),
                template_type=template_data.get("template_type") or "auto",
                field_rules=[
                    FieldRule.from_dict(field)
                    for field in template_data.get("field_rules", [])
                    if isinstance(field, dict)
                ],
                next_page_selector=template_data.get("next_page_selector") or "",
                notes=template_data.get("notes") or "由 AI 任务计划生成。",
            )
            self.upsert_template(template)
        options = result.get("options", {}) if isinstance(result, dict) else {}
        if options:
            self.use_browser_checkbox.setChecked(bool(options.get("use_browser", True)))
            self.scroll_times_input.setValue(int(options.get("scroll_times", self.scroll_times_input.value()) or 0))
            self.page_limit_input.setValue(int(options.get("page_limit", self.page_limit_input.value()) or 1))
            self.subpage_limit_input.setValue(int(options.get("subpage_limit", self.subpage_limit_input.value()) or 0))
            self.subpage_checkbox.setChecked(self.subpage_limit_input.value() > 0)
        self.show_main_tab("批量采集")
        self.append_ai_output("AI 采集任务计划已应用到当前界面。")
        return True

    def show_wizard_analysis_table(self, plan):
        if not isinstance(plan, dict):
            return
        signals = plan.get("signals", {}) or {}
        rows = [
            ["页面类型", plan.get("page_kind", ""), "向导判断当前网页属于哪类采集任务"],
            ["推荐模板", plan.get("template_name", ""), "已自动套用到模板和采集任务"],
            [
                "模型用途",
                (plan.get("use_case") or {}).get("name", ""),
                f"{(plan.get('use_case') or {}).get('provider', '')} / {(plan.get('use_case') or {}).get('model', '')}",
            ],
            ["置信度", f"{plan.get('confidence', '')}%", "越高表示页面线索越明确"],
            ["链接数量", signals.get("links", 0), "用于判断列表页和子页面深抓"],
            ["疑似详情链接", signals.get("detail_like_links", 0), "数量越多越适合开启子页面抓取"],
            ["图片数量", signals.get("images", 0), "图片较多时建议使用真实浏览器和滚动"],
            ["表单控件", signals.get("forms", 0), "可能需要网页 Agent 或登录浏览器"],
            ["表格数量", signals.get("tables", 0), "表格页可直接网页转表格"],
        ]
        self.latest_wizard_analysis_rows = rows
        self.fill_ai_table(["项目", "结果", "说明"], rows)

    def copy_current_ai_task_plan(self):
        result = self.latest_ai_result if isinstance(self.latest_ai_result, dict) else {}
        if not result:
            QMessageBox.information(self, "提示", "请先生成自然语言采集任务。")
            return
        text = json.dumps(result, ensure_ascii=False, indent=2)
        clipboard = QApplication.clipboard()
        clipboard.clear()
        clipboard.setText(text, mode=QClipboard.Mode.Clipboard)
        self.last_clipboard_text = text
        QApplication.processEvents()
        self.append_ai_output("已复制自然语言任务计划 JSON。")

    def apply_ai_table_result(self, result):
        if not isinstance(result, dict):
            return
        columns = result.get("columns") or []
        rows = result.get("rows") or []
        self.fill_ai_table(columns, rows)

    def fill_ai_table(self, columns, rows):
        self.ai_table.setRowCount(0)
        self.ai_table.setColumnCount(len(columns))
        self.ai_table.setHorizontalHeaderLabels([str(item) for item in columns])
        for source_row in rows:
            row = self.ai_table.rowCount()
            self.ai_table.insertRow(row)
            values = source_row if isinstance(source_row, list) else [source_row]
            for column, value in enumerate(values[: len(columns)]):
                self.ai_table.setItem(row, column, QTableWidgetItem(str(value)))
        for column in range(len(columns)):
            self.ai_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)

    def ai_table_data(self):
        columns = []
        for column in range(self.ai_table.columnCount()):
            header = self.ai_table.horizontalHeaderItem(column)
            columns.append(header.text() if header else f"字段{column + 1}")
        rows = []
        for row in range(self.ai_table.rowCount()):
            values = []
            for column in range(self.ai_table.columnCount()):
                item = self.ai_table.item(row, column)
                values.append(item.text() if item else "")
            rows.append(values)
        return columns, rows

    def export_ai_table(self):
        columns, rows = self.ai_table_data()
        if not columns or not rows:
            QMessageBox.information(self, "提示", "AI 表格里没有可导出的数据。")
            return
        file_path, selected = QFileDialog.getSaveFileName(
            self,
            "导出 AI 表格",
            os.path.join(os.getcwd(), "AI表格结果.xlsx"),
            "Excel 文件 (*.xlsx);;CSV 文件 (*.csv);;JSON 文件 (*.json)",
        )
        if not file_path:
            return
        file_path = selected_export_path(file_path, selected)
        try:
            export_table_data(file_path, columns, rows, sheet_name="AI表格结果")
        except Exception as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        self.append_ai_output(f"AI 表格已导出：{file_path}")
        QMessageBox.information(self, "导出成功", f"已导出：\n{file_path}")

    def copy_ai_table_to_clipboard(self):
        columns, rows = self.ai_table_data()
        if not columns or not rows:
            QMessageBox.information(self, "提示", "AI 表格里没有可复制的数据。")
            return
        clipboard = QApplication.clipboard()
        clipboard.clear()
        copied_text = table_data_to_tsv(columns, rows)
        clipboard.setText(copied_text, mode=QClipboard.Mode.Clipboard)
        self.last_clipboard_text = copied_text
        QApplication.processEvents()
        self.append_ai_output(f"已复制 AI 表格：{len(rows)} 行，{len(columns)} 列。")

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
            os.getcwd(),
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

    def current_run_config(self, urls, runtime_overrides=None):
        runtime_overrides = runtime_overrides or {}
        scrape_subpages = bool(runtime_overrides.get("scrape_subpages", self.subpage_checkbox.isChecked()))
        subpage_limit = int(runtime_overrides.get("subpage_limit", self.subpage_limit_input.value()) or 0)
        skip_unchanged = bool(runtime_overrides.get("skip_unchanged", self.skip_unchanged_checkbox.isChecked()))
        selected_subpages = runtime_overrides.get(
            "selected_subpage_urls",
            self.selected_subpage_urls if self.subpage_checkbox.isChecked() else [],
        )
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
            "ai_provider": self.ai_settings.get("provider", ""),
            "model": self.ai_settings.get("model", ""),
            "risk_checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    def run_preflight_check(self):
        risks = self.collect_preflight_risks()
        self.fill_risk_table(risks)
        high_count = sum(1 for item in risks if item.get("级别") in ("高", "需处理"))
        if high_count:
            self.append_log(f"抓取前检查完成：发现 {high_count} 个高风险/需处理项。")
        else:
            self.append_log("抓取前检查完成：未发现明显高风险配置。")
        return risks

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

    def unconfirmed_preflight_risks(self, risks):
        confirmed_keys = self.active_risk_confirmation_keys(risks)
        urls = self.urls_from_input()
        return [
            item for item in self.remaining_confirmation_risks(risks)
            if risk_confirmation_key(urls, item) not in confirmed_keys
        ]

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

    def selected_template_name(self):
        return self.template_combo.currentText()

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
        self.fill_task_queue_table(self.estimated_task_queue(urls, runtime_overrides))
        self.refresh_new_user_flow_status("running")
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
            run_id=self.current_run_id,
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

    def stop_collecting(self):
        if self.worker:
            self.worker.stop()
            self.set_collecting_buttons_state(True)
            if hasattr(self, "simple_status_label"):
                self.simple_status_label.setText("正在停止采集，已采到的结果会保留")
            if hasattr(self, "simple_progress_label"):
                self.simple_progress_label.setText("后台：正在安全停止，请稍等当前网页返回")
            self.append_log("正在停止采集。")

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
        self.database.finish_run(
            self.current_run_id,
            status=status,
            result_count=result_count,
            notes=notes,
        )
        if self.active_schedule_id:
            schedule_status = "完成" if status == "finished" else f"结束：{status}"
            self.mark_schedule_run(self.active_schedule_id, schedule_status, notes, count_run=True)
            self.active_schedule_id = ""
        final_progress = dict(progress)
        final_progress["status"] = status
        if final_progress:
            self.update_collect_progress(final_progress)
        self.persist_current_run_queue_snapshot()
        self.worker = None
        self.worker_thread = None
        self.current_run_id = None
        self.current_run_strategy_label = ""
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

    def add_record(self, record):
        if getattr(self, "current_run_strategy_label", "") and not record.get("simple_collect_depth"):
            record["simple_collect_depth"] = self.current_run_strategy_label
        self.ensure_record_completeness(record)
        self.records.append(record)
        record_index = len(self.records) - 1
        self.add_record_to_table(self.result_table, record, "current", len(self.records) - 1)
        if hasattr(self, "simple_result_table"):
            merged_to_parent = False
            if getattr(self, "simple_merge_subpage_results", False):
                parent_index = self.simple_find_parent_record_index(record)
                if parent_index >= 0:
                    parent_record = self.records[parent_index]
                    merged_to_parent = self.simple_merge_subpage_into_parent(parent_record, record)
                    if merged_to_parent:
                        self.ensure_record_completeness(parent_record, force=True)
                        for row in range(self.simple_result_table.rowCount()):
                            marker = self.simple_result_table.item(row, 0)
                            if marker and marker.data(Qt.ItemDataRole.UserRole + 1) == parent_index:
                                self.simple_refresh_result_row(row, parent_record, parent_index)
                                self.simple_result_table.selectRow(row)
                                break
                        self.append_log(f"已把详情页资料合并到主结果：{compact_text(parent_record.get('title') or parent_record.get('url'), 80)}")
            if not merged_to_parent:
                self.add_record_to_simple_table(record, record_index)
                if self.simple_result_table.rowCount() == 1:
                    self.simple_result_table.selectRow(0)
            self.update_simple_result_preview()
            self.refresh_simple_field_table()
            self.simple_status_label.setText(f"已采到 {len(self.records)} 条结果")
            self.set_simple_flow_step("导出")
            self.refresh_simple_result_summary()
        self.refresh_result_status_summary()
        self.fill_result_quality_table()
        self.refresh_new_user_flow_status("export")
        self.update_queue_result_summary_for_record(record)
        self.update_low_quality_retry_report(record)

    def record_status_text(self, record):
        if record.get("error"):
            return "错误"
        if record.get("duplicate"):
            return "重复"
        if record.get("changed"):
            return "变化"
        return "新增"

    def style_record_row(self, table, row, record):
        status = self.record_status_text(record)
        palette = {
            "错误": ("#fff1f0", "#a8071a"),
            "变化": ("#fffbe6", "#ad6800"),
            "重复": ("#f5f5f5", "#595959"),
            "新增": ("#f6ffed", "#237804"),
        }
        background, foreground = palette.get(status, ("#ffffff", "#262626"))
        status_column = FIELD_HEADERS.index("是否变化") if "是否变化" in FIELD_HEADERS else FIELD_HEADERS.index("变化")
        error_column = FIELD_HEADERS.index("错误")
        important_columns = {
            status_column,
            error_column,
        }
        for column in range(table.columnCount()):
            item = table.item(row, column)
            if not item:
                continue
            item.setBackground(QColor(background))
            if column in important_columns:
                item.setForeground(QColor(foreground))
                if status == "错误" and column == error_column:
                    item.setForeground(QColor("#a8071a"))

    def refresh_result_status_summary(self):
        if not hasattr(self, "result_status_label"):
            return
        if not self.records:
            self.result_status_label.setText("结果状态：等待采集")
            if hasattr(self, "result_export_hint_label"):
                self.result_export_hint_label.setText("导出引导：采到结果后可导出 Excel 或复制到 Sheets")
            return
        counts = {"新增": 0, "变化": 0, "重复": 0, "错误": 0}
        for record in self.records:
            counts[self.record_status_text(record)] = counts.get(self.record_status_text(record), 0) + 1
        parts = [f"{name} {count}" for name, count in counts.items() if count]
        self.result_status_label.setText(f"结果状态：共 {len(self.records)} 条｜" + "｜".join(parts))
        if hasattr(self, "result_export_hint_label"):
            image_count = sum(len(record.get("images", []) or []) for record in self.records)
            image_text = f"；发现 {image_count} 张图片，可到高级设置下载图片" if image_count else ""
            self.result_export_hint_label.setText(
                f"导出引导：已可导出 Excel，或复制到 Sheets；选中行可打开原网页{image_text}"
            )

    def add_record_to_table(self, table, record, source="current", record_index=None):
        self.ensure_record_completeness(record)
        row = table.rowCount()
        table.insertRow(row)
        status_text = self.record_status_text(record)
        values = [
            record.get("collected_at", ""),
            record.get("url", ""),
            record.get("domain", ""),
            record.get("template_name", ""),
            record.get("title", ""),
            record.get("price", ""),
            record.get("published_time", ""),
            record.get("author", ""),
            record.get("body", ""),
            str(len(record.get("images", []) or [])),
            str(len(record.get("links", []) or [])),
            str(len(record.get("tables", []) or [])),
            record.get("completeness_label", ""),
            "、".join(record.get("completeness_missing", []) or []),
            record.get("fingerprint", "")[:16],
            status_text,
            record.get("error", ""),
        ]
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setToolTip(str(value))
            if column == 0:
                item.setData(Qt.ItemDataRole.UserRole, source)
                item.setData(
                    Qt.ItemDataRole.UserRole + 1,
                    record_index if record_index is not None else row,
                )
            table.setItem(row, column, item)
        self.style_record_row(table, row, record)

    def selected_record_from_table(self, table):
        selected = table.selectedIndexes()
        if not selected:
            return None
        row = selected[0].row()
        marker = table.item(row, 0)
        if marker:
            source = marker.data(Qt.ItemDataRole.UserRole)
            index = marker.data(Qt.ItemDataRole.UserRole + 1)
            if source == "current" and isinstance(index, int) and 0 <= index < len(self.records):
                return self.records[index]
            if source == "history" and isinstance(index, int) and 0 <= index < len(self.history_records):
                return self.history_records[index]
        url_item = table.item(row, 1)
        url = url_item.text() if url_item else ""
        for record in self.records + self.history_records + self.database.recent_records(500):
            if record.get("url") == url:
                return record
        return None

    def update_current_detail(self):
        source = self.sender()
        if source is getattr(self, "simple_result_table", None):
            record = self.selected_record_from_table(self.simple_result_table)
        else:
            record = self.selected_record_from_table(self.result_table)
        self.update_detail_panel(record)

    def update_history_detail(self):
        record = self.selected_record_from_table(self.history_table)
        if not record:
            self.history_detail_title_label.setText("未选择历史记录")
            self.history_detail_body_output.clear()
            self.history_detail_link_table.setRowCount(0)
            self.history_detail_table_view.setRowCount(0)
            self.history_detail_table_view.setColumnCount(0)
            return
        self.history_detail_title_label.setText(
            f"{record.get('title', '') or '(无标题)'}\n{record.get('url', '')}"
        )
        self.history_detail_body_output.setPlainText(record.get("body", ""))
        self.fill_link_table(self.history_detail_link_table, record.get("links", []) or [])
        self.fill_table_widget(self.history_detail_table_view, record.get("tables", []) or [])

    def update_detail_panel(self, record):
        if not record:
            self.detail_title_label.setText("未选择结果")
            self.detail_url_label.setText("")
            self.detail_meta_label.setText("")
            self.detail_body_output.clear()
            self.clear_image_preview()
            self.detail_link_table.setRowCount(0)
            self.detail_table_view.setRowCount(0)
            self.detail_table_view.setColumnCount(0)
            return
        self.detail_title_label.setText(record.get("title", "") or "(无标题)")
        self.detail_url_label.setText(record.get("url", ""))
        meta_parts = [
            f"域名：{record.get('domain', '')}",
            f"模板：{record.get('template_name', '')}",
            f"价格：{record.get('price', '')}",
            f"时间：{record.get('published_time', '')}",
            f"作者：{record.get('author', '')}",
            f"状态：{self.record_status_text(record)}",
        ]
        self.detail_meta_label.setText(" | ".join(part for part in meta_parts if part.split("：", 1)[1]))
        self.detail_body_output.setPlainText(record.get("body", ""))
        self.update_image_preview(record.get("images", []) or [])
        self.update_link_preview(record.get("links", []) or [])
        self.update_table_preview(record.get("tables", []) or [])

    def clear_image_preview(self):
        while self.image_layout.count():
            item = self.image_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.image_layout.addStretch(1)

    def update_image_preview(self, images):
        self.clear_image_preview()
        for image in images[:8]:
            image_url = image.get("url", "") if isinstance(image, dict) else str(image)
            label = QLabel()
            label.setFixedSize(112, 92)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setToolTip(image_url)
            pixmap = self.load_image_pixmap(image_url)
            if pixmap and not pixmap.isNull():
                label.setPixmap(
                    pixmap.scaled(
                        108,
                        88,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            else:
                label.setText("图片")
            self.image_layout.insertWidget(self.image_layout.count() - 1, label)

    def load_image_pixmap(self, image_url):
        if not image_url:
            return None
        try:
            request = Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(request, timeout=5) as response:
                data = response.read(1024 * 1024)
        except Exception:
            return None
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            return pixmap
        return None

    def update_link_preview(self, links):
        self.fill_link_table(self.detail_link_table, links)

    def fill_link_table(self, table, links):
        table.setRowCount(0)
        for link in links[:50]:
            if isinstance(link, dict):
                text = link.get("text", "")
                url = link.get("url", "")
            else:
                text = ""
                url = str(link)
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(text))
            table.setItem(row, 1, QTableWidgetItem(url))

    def update_table_preview(self, tables):
        self.fill_table_widget(self.detail_table_view, tables)

    def fill_table_widget(self, table_widget, tables):
        table_widget.setRowCount(0)
        table_widget.setColumnCount(0)
        if not tables:
            return
        first_table = tables[0]
        if not isinstance(first_table, list) or not first_table:
            return
        column_count = max((len(row) for row in first_table if isinstance(row, list)), default=0)
        table_widget.setColumnCount(column_count)
        for source_row in first_table[:100]:
            if not isinstance(source_row, list):
                continue
            row = table_widget.rowCount()
            table_widget.insertRow(row)
            for column, value in enumerate(source_row[:column_count]):
                table_widget.setItem(row, column, QTableWidgetItem(str(value)))

    def open_selected_url(self):
        record = self.selected_record_from_table(self.result_table)
        if not record:
            QMessageBox.information(self, "提示", "请先选择一条结果。")
            return
        QDesktopServices.openUrl(QUrl(record.get("url", "")))

    def clear_current_results(self):
        self.records.clear()
        self.result_table.setRowCount(0)
        if hasattr(self, "simple_result_table"):
            self.simple_result_table.setRowCount(0)
        self.simple_merge_subpage_results = False
        self.simple_subpage_parent_map = {}
        if hasattr(self, "simple_preview_title_label"):
            self.update_simple_result_preview()
        if hasattr(self, "simple_field_table"):
            self.refresh_simple_field_table()
        if hasattr(self, "simple_status_label"):
            self.simple_status_label.setText("准备就绪")
        if hasattr(self, "simple_progress_label"):
            self.simple_progress_label.setText("流程：输入网址 -> 开始采集 -> 导出结果")
        self.low_quality_retry_baseline = {}
        self.low_quality_retry_active = False
        self.low_quality_retry_report_rows = []
        self.latest_crawl_discovery_messages = []
        self.refresh_low_quality_retry_report_summary()
        if hasattr(self, "simple_discovery_label"):
            self.simple_discovery_label.setText("发现记录：等待采集")
        self.set_simple_flow_step("输入")
        self.refresh_simple_result_summary()
        self.refresh_result_status_summary()
        self.fill_result_quality_table([])
        self.refresh_new_user_flow_status("prepared")

    def generate_change_report(self):
        self.change_report_rows = self.database.change_report(500)
        self.fill_change_report_table(self.change_report_rows)
        if self.change_report_rows:
            self.append_log(f"已生成 {len(self.change_report_rows)} 条网页监控变更记录。")
        else:
            self.append_log("暂未发现变化记录。重复采集同一网址且内容变化后会出现在这里。")

    def fill_change_report_table(self, rows):
        columns = ["监控时间", "网址", "域名", "字段", "旧值", "新值", "标题"]
        self.change_report_table.setRowCount(0)
        for source in rows:
            row = self.change_report_table.rowCount()
            self.change_report_table.insertRow(row)
            for column, key in enumerate(columns):
                value = source.get(key, "")
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.change_report_table.setItem(row, column, item)

    def build_change_alert_rows(self, limit=500):
        alerts = []
        for source in self.database.change_report(limit):
            alert_id = change_alert_key(source)
            state = self.change_alert_states.get(alert_id, {})
            alert = {
                "处理状态": state.get("status", "未读"),
                "类型": "变化",
                "监控时间": source.get("监控时间", ""),
                "网址": source.get("网址", ""),
                "字段": source.get("字段", ""),
                "旧值": source.get("旧值", ""),
                "新值": source.get("新值", ""),
                "标题": source.get("标题", ""),
                "域名": source.get("域名", ""),
                "ID": alert_id,
                "状态更新时间": state.get("updated_at", ""),
            }
            alerts.append(alert)
        return alerts

    def refresh_change_alerts(self, silent=False, notify=False):
        self.change_alert_states = load_change_alert_states()
        self.change_alert_rows = self.build_change_alert_rows(500)
        self.fill_change_alert_table(self.change_alert_rows)
        count = len(self.change_alert_rows)
        if count:
            fields = sorted({item.get("字段", "") for item in self.change_alert_rows if item.get("字段")})
            field_text = "、".join(fields[:5]) or "字段"
            unread = sum(1 for item in self.change_alert_rows if item.get("处理状态") == "未读")
            handled = sum(1 for item in self.change_alert_rows if item.get("处理状态") == "已处理")
            ignored = sum(1 for item in self.change_alert_rows if item.get("处理状态") == "忽略")
            self.change_alert_status_label.setText(
                f"发现 {count} 条变更提醒，未读 {unread}，已处理 {handled}，忽略 {ignored}；涉及：{field_text}"
            )
            if notify and unread:
                latest_unread = next((item for item in self.change_alert_rows if item.get("处理状态") == "未读"), {})
                self.notify_unread_change_alerts(unread, latest_unread)
            if not silent:
                self.append_log(f"已刷新 {count} 条变更提醒。")
        else:
            self.change_alert_status_label.setText("暂无变更提醒；同一网址再次采集且内容变化后会显示。")
            if not silent:
                self.append_log("暂无变更提醒。")
        self.refresh_overview()
        return count

    def fill_change_alert_table(self, rows):
        columns = ["处理状态", "类型", "监控时间", "网址", "字段", "旧值", "新值", "标题", "域名", "ID"]
        status_filter = self.change_alert_filter_combo.currentText() if hasattr(self, "change_alert_filter_combo") else "全部提醒"
        self.change_alert_table.setRowCount(0)
        for source in rows:
            if status_filter != "全部提醒" and source.get("处理状态") != status_filter:
                continue
            row = self.change_alert_table.rowCount()
            self.change_alert_table.insertRow(row)
            for column, key in enumerate(columns):
                value = source.get(key, "")
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if key == "处理状态" and value == "未读":
                    item.setBackground(Qt.GlobalColor.yellow)
                elif key == "处理状态" and value == "已处理":
                    item.setBackground(Qt.GlobalColor.green)
                elif key == "处理状态" and value == "忽略":
                    item.setBackground(Qt.GlobalColor.lightGray)
                self.change_alert_table.setItem(row, column, item)

    def selected_change_alert_id(self):
        selected_rows = sorted({index.row() for index in self.change_alert_table.selectedIndexes()})
        if not selected_rows:
            return ""
        row = selected_rows[0]
        id_item = self.change_alert_table.item(row, 9)
        return id_item.text().strip() if id_item else ""

    def set_selected_change_alert_status(self, status):
        alert_id = self.selected_change_alert_id()
        if not alert_id:
            QMessageBox.information(self, "提示", "请先选择一条变更提醒。")
            return
        self.change_alert_states = load_change_alert_states()
        self.change_alert_states[alert_id] = {
            "status": status,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "note": "",
        }
        self.change_alert_states = save_change_alert_states(self.change_alert_states)
        self.refresh_change_alerts(silent=True)
        self.refresh_overview()
        self.append_log(f"已将变更提醒标记为：{status}。")

    def run_status_text(self, status):
        return {
            "running": "运行中",
            "finished": "已完成",
            "stopped": "已停止",
            "failed": "失败",
            "partial": "部分成功",
        }.get(status or "", status or "")

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
        self.append_log(f"已复用任务档案 #{run.get('id')} 的网址、模板、分页、子页面和 AI 配置。")
        return True

    def view_selected_run_queue_result(self):
        url = self.selected_queue_url(self.run_detail_queue_table)
        if not url:
            QMessageBox.information(self, "提示", "请先选择一个任务队列项。")
            return
        if not self.select_record_by_url(self.run_detail_result_table, url):
            QMessageBox.information(self, "提示", "当前任务结果里还没有这个队列项的结果。")
            return

    def reuse_selected_run_config(self):
        if self.apply_run_config(self.selected_run_record()):
            self.show_history_section("采集历史")

    def rerun_selected_task(self):
        if self.worker:
            QMessageBox.information(self, "提示", "已有采集任务正在运行，请稍后再重跑。")
            return
        run = self.selected_run_record()
        if self.apply_run_config(run):
            self.append_log(f"按任务档案 #{run.get('id')} 重新开始采集。")
            self.start_collecting()

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

    def selected_market_template_item(self):
        row = self.template_market_table.currentRow() if hasattr(self, "template_market_table") else -1
        if row < 0 or row >= len(getattr(self, "template_market_items", [])):
            return None
        return self.template_market_items[row]

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

    def select_template_by_name(self, template_name):
        index = self.template_combo.findText(template_name)
        if index >= 0:
            self.template_combo.setCurrentIndex(index)
        list_items = self.template_list.findItems(template_name, Qt.MatchFlag.MatchExactly)
        if list_items:
            self.template_list.setCurrentItem(list_items[0])
        return index >= 0

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

    def remove_selected_field(self):
        rows = sorted({index.row() for index in self.field_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.field_table.removeRow(row)

    def new_template(self):
        template = SiteTemplate(
            name=f"新模板{len(self.templates) + 1}",
            domain="",
            template_type="auto",
        )
        self.templates.append(template)
        self.template_store.save(self.templates)
        self.reload_templates()
        self.template_list.setCurrentRow(len(self.templates) - 1)

    def apply_scene_preset(self):
        preset_name = self.scene_preset_combo.currentText()
        preset = scene_template_presets().get(preset_name)
        if not preset:
            QMessageBox.information(self, "提示", "请选择一个场景模板。")
            return
        self.template_name_input.setText(preset.name)
        self.template_domain_input.setText(preset.domain)
        index = self.template_type_combo.findData(preset.template_type)
        self.template_type_combo.setCurrentIndex(max(0, index))
        self.next_page_selector_input.setText(preset.next_page_selector)
        self.template_notes_input.setPlainText(preset.notes)
        self.field_table.setRowCount(0)
        for rule in preset.field_rules:
            self.add_field_row(rule)
        self.append_log(f"已套用场景模板：{preset.name}，可直接保存或开始采集。")

    def collect_field_rules_from_table(self):
        rules = []
        for row in range(self.field_table.rowCount()):
            name_item = self.field_table.item(row, 0)
            selector_item = self.field_table.item(row, 1)
            attr_widget = self.field_table.cellWidget(row, 2)
            multi_widget = self.field_table.cellWidget(row, 3)
            name = name_item.text().strip() if name_item else ""
            selector = selector_item.text().strip() if selector_item else ""
            if not name or not selector:
                continue
            attr = attr_widget.currentText() if isinstance(attr_widget, QComboBox) else "text"
            multiple = multi_widget.isChecked() if isinstance(multi_widget, QCheckBox) else False
            rules.append(FieldRule(name, selector, attr, multiple))
        return rules

    def save_current_template(self):
        row = self.template_list.currentRow()
        if row < 0:
            return
        template = SiteTemplate(
            name=self.template_name_input.text().strip() or "未命名模板",
            domain=self.template_domain_input.text().strip().lower(),
            template_type=self.template_type_combo.currentData() or "auto",
            field_rules=self.collect_field_rules_from_table(),
            next_page_selector=self.next_page_selector_input.text().strip(),
            notes=self.template_notes_input.toPlainText().strip(),
        )
        self.templates[row] = template
        self.template_store.save(self.templates)
        self.reload_templates()
        self.template_list.setCurrentRow(row)
        self.select_template_by_name(template.name)
        self.append_log(f"已保存模板：{template.name}")

    def delete_current_template(self):
        row = self.template_list.currentRow()
        if row < 0:
            return
        if len(self.templates) <= 1:
            QMessageBox.information(self, "提示", "至少保留一个模板。")
            return
        del self.templates[row]
        self.template_store.save(self.templates)
        self.reload_templates()

    def generate_selector_from_helper(self):
        selector = build_selector_from_clicked_element(
            self.click_tag_input.text(),
            self.click_id_input.text(),
            self.click_class_input.text().split(),
        )
        selected_rows = {index.row() for index in self.field_table.selectedIndexes()}
        if selected_rows:
            row = min(selected_rows)
        else:
            self.add_field_row(FieldRule("自定义字段", selector))
            row = self.field_table.rowCount() - 1
        self.field_table.setItem(row, 1, QTableWidgetItem(selector))
        self.append_log(f"已生成选择器：{selector}")

    def visual_pick_field(self):
        url = normalize_url(self.pick_url_input.text())
        if not url:
            urls = self.urls_from_input()
            url = urls[0] if urls else ""
        if not url:
            QMessageBox.information(self, "提示", "请先输入点选网址或采集任务网址。")
            return
        field_name = self.pick_field_name_input.text().strip() or "自定义字段"
        self.append_log(f"正在打开点选浏览器：{url}")
        try:
            result = pick_element_from_page(url)
        except Exception as exc:
            QMessageBox.warning(self, "点选失败", str(exc))
            return
        if not result:
            self.append_log("点选已取消或未获得结果。")
            return
        self.click_tag_input.setText(result.get("tag", ""))
        self.click_id_input.setText(result.get("id", ""))
        self.click_class_input.setText(" ".join(result.get("classes", [])))
        selector = result.get("selector") or build_selector_from_clicked_element(
            result.get("tag", ""),
            result.get("id", ""),
            result.get("classes", []),
        )
        attr = "text"
        if result.get("tag") == "img":
            attr = "src"
        elif result.get("tag") == "a":
            attr = "href"
        self.add_field_row(FieldRule(field_name, selector, attr, False))
        self.append_log(
            f"已添加点选字段：{field_name} -> {selector} | "
            f"{result.get('text', '')[:80]}"
        )


from ui_ai_settings import build_ai_tab as _build_ai_tab
from ui_history import (
    build_history_detail_panel as _build_history_detail_panel,
    build_history_tab as _build_history_tab,
    build_run_detail_panel as _build_run_detail_panel,
)
from ui_exports import (
    copy_current_results_to_sheets as _copy_current_results_to_sheets,
    copy_history_results_to_sheets as _copy_history_results_to_sheets,
    copy_records_to_sheets as _copy_records_to_sheets,
    export_change_alerts as _export_change_alerts,
    export_change_alerts_to_file as _export_change_alerts_to_file,
    export_change_report as _export_change_report,
    export_current_results as _export_current_results,
    export_history_results as _export_history_results,
    export_records_dialog as _export_records_dialog,
    export_run_records as _export_run_records,
    export_selected_run_results as _export_selected_run_results,
)
from ui_queue import (
    apply_task_queue_filters as _apply_task_queue_filters,
    copy_selected_queue_error as _copy_selected_queue_error,
    enable_browser_recovery as _enable_browser_recovery,
    estimate_current_task as _estimate_current_task,
    estimated_task_queue as _estimated_task_queue,
    fill_queue_snapshot_table as _fill_queue_snapshot_table,
    fill_task_queue_table as _fill_task_queue_table,
    filtered_task_queue_rows as _filtered_task_queue_rows,
    has_timeout_queue_failure as _has_timeout_queue_failure,
    incomplete_queue_urls as _incomplete_queue_urls,
    persist_current_run_queue_snapshot as _persist_current_run_queue_snapshot,
    queue_record_summary as _queue_record_summary,
    queue_status_counts as _queue_status_counts,
    refresh_failure_recovery_panel as _refresh_failure_recovery_panel,
    retry_incomplete_queue_items as _retry_incomplete_queue_items,
    retry_selected_queue_item as _retry_selected_queue_item,
    select_record_by_url as _select_record_by_url,
    selected_queue_error_text as _selected_queue_error_text,
    selected_queue_row_data as _selected_queue_row_data,
    selected_queue_url as _selected_queue_url,
    slow_down_recovery as _slow_down_recovery,
    task_queue_snapshot as _task_queue_snapshot,
    update_collect_progress as _update_collect_progress,
    update_queue_detail_panel as _update_queue_detail_panel,
    update_queue_result_summary_for_record as _update_queue_result_summary_for_record,
    update_queue_summary as _update_queue_summary,
    update_task_queue_progress as _update_task_queue_progress,
    view_selected_queue_result as _view_selected_queue_result,
)
from ui_ai_history import (
    ai_call_log_table_data as _ai_call_log_table_data,
    ai_call_summary_table_data as _ai_call_summary_table_data,
    ai_repair_history_table_data as _ai_repair_history_table_data,
    apply_ai_repair_history_entry as _apply_ai_repair_history_entry,
    apply_best_ai_repair_history as _apply_best_ai_repair_history,
    apply_repair_history_fields as _apply_repair_history_fields,
    apply_selected_ai_repair_fields as _apply_selected_ai_repair_fields,
    apply_selected_ai_repair_history as _apply_selected_ai_repair_history,
    build_repair_history_diff_rows as _build_repair_history_diff_rows,
    clear_ai_call_logs_and_refresh as _clear_ai_call_logs_and_refresh,
    compare_ai_repair_history_entry as _compare_ai_repair_history_entry,
    compare_selected_ai_repair_history as _compare_selected_ai_repair_history,
    confirm_clear_ai_call_logs as _confirm_clear_ai_call_logs,
    export_ai_call_logs as _export_ai_call_logs,
    export_ai_call_logs_to_file as _export_ai_call_logs_to_file,
    export_ai_call_summary as _export_ai_call_summary,
    export_ai_call_summary_to_file as _export_ai_call_summary_to_file,
    export_ai_repair_history as _export_ai_repair_history,
    export_ai_repair_history_to_file as _export_ai_repair_history_to_file,
    field_rules_from_history_entry as _field_rules_from_history_entry,
    fill_ai_call_log_table as _fill_ai_call_log_table,
    fill_ai_call_summary_table as _fill_ai_call_summary_table,
    fill_repair_history_diff_table as _fill_repair_history_diff_table,
    refresh_ai_call_logs as _refresh_ai_call_logs,
    refresh_ai_call_summary as _refresh_ai_call_summary,
    refresh_ai_repair_history as _refresh_ai_repair_history,
    repair_field_rule_signature as _repair_field_rule_signature,
    repair_history_score as _repair_history_score,
    selected_ai_repair_history_entry as _selected_ai_repair_history_entry,
    selected_repair_diff_fields as _selected_repair_diff_fields,
)
from ui_export_utils import selected_export_path


UniversalMainWindow.build_ai_tab = _build_ai_tab
UniversalMainWindow.build_history_tab = _build_history_tab
UniversalMainWindow.build_history_detail_panel = _build_history_detail_panel
UniversalMainWindow.build_run_detail_panel = _build_run_detail_panel
UniversalMainWindow.export_current_results = _export_current_results
UniversalMainWindow.copy_records_to_sheets = _copy_records_to_sheets
UniversalMainWindow.copy_current_results_to_sheets = _copy_current_results_to_sheets
UniversalMainWindow.export_history_results = _export_history_results
UniversalMainWindow.copy_history_results_to_sheets = _copy_history_results_to_sheets
UniversalMainWindow.export_change_alerts_to_file = _export_change_alerts_to_file
UniversalMainWindow.export_change_report = _export_change_report
UniversalMainWindow.export_change_alerts = _export_change_alerts
UniversalMainWindow.export_run_records = _export_run_records
UniversalMainWindow.export_selected_run_results = _export_selected_run_results
UniversalMainWindow.export_records_dialog = _export_records_dialog
UniversalMainWindow.task_queue_snapshot = _task_queue_snapshot
UniversalMainWindow.persist_current_run_queue_snapshot = _persist_current_run_queue_snapshot
UniversalMainWindow.estimated_task_queue = _estimated_task_queue
UniversalMainWindow.filtered_task_queue_rows = _filtered_task_queue_rows
UniversalMainWindow.apply_task_queue_filters = _apply_task_queue_filters
UniversalMainWindow.queue_status_counts = _queue_status_counts
UniversalMainWindow.update_queue_summary = _update_queue_summary
UniversalMainWindow.refresh_failure_recovery_panel = _refresh_failure_recovery_panel
UniversalMainWindow.enable_browser_recovery = _enable_browser_recovery
UniversalMainWindow.slow_down_recovery = _slow_down_recovery
UniversalMainWindow.selected_queue_row_data = _selected_queue_row_data
UniversalMainWindow.update_queue_detail_panel = _update_queue_detail_panel
UniversalMainWindow.fill_queue_snapshot_table = _fill_queue_snapshot_table
UniversalMainWindow.fill_task_queue_table = _fill_task_queue_table
UniversalMainWindow.queue_record_summary = _queue_record_summary
UniversalMainWindow.update_queue_result_summary_for_record = _update_queue_result_summary_for_record
UniversalMainWindow.select_record_by_url = _select_record_by_url
UniversalMainWindow.selected_queue_url = _selected_queue_url
UniversalMainWindow.selected_queue_error_text = _selected_queue_error_text
UniversalMainWindow.view_selected_queue_result = _view_selected_queue_result
UniversalMainWindow.retry_selected_queue_item = _retry_selected_queue_item
UniversalMainWindow.copy_selected_queue_error = _copy_selected_queue_error
UniversalMainWindow.incomplete_queue_urls = _incomplete_queue_urls
UniversalMainWindow.has_timeout_queue_failure = _has_timeout_queue_failure
UniversalMainWindow.retry_incomplete_queue_items = _retry_incomplete_queue_items
UniversalMainWindow.estimate_current_task = _estimate_current_task
UniversalMainWindow.update_collect_progress = _update_collect_progress
UniversalMainWindow.update_task_queue_progress = _update_task_queue_progress
UniversalMainWindow.refresh_ai_call_logs = _refresh_ai_call_logs
UniversalMainWindow.fill_ai_call_log_table = _fill_ai_call_log_table
UniversalMainWindow.refresh_ai_call_summary = _refresh_ai_call_summary
UniversalMainWindow.fill_ai_call_summary_table = _fill_ai_call_summary_table
UniversalMainWindow.ai_call_log_table_data = _ai_call_log_table_data
UniversalMainWindow.export_ai_call_logs_to_file = _export_ai_call_logs_to_file
UniversalMainWindow.ai_call_summary_table_data = _ai_call_summary_table_data
UniversalMainWindow.export_ai_call_summary_to_file = _export_ai_call_summary_to_file
UniversalMainWindow.ai_repair_history_table_data = _ai_repair_history_table_data
UniversalMainWindow.refresh_ai_repair_history = _refresh_ai_repair_history
UniversalMainWindow.repair_history_score = _repair_history_score
UniversalMainWindow.selected_ai_repair_history_entry = _selected_ai_repair_history_entry
UniversalMainWindow.field_rules_from_history_entry = _field_rules_from_history_entry
UniversalMainWindow.repair_field_rule_signature = _repair_field_rule_signature
UniversalMainWindow.build_repair_history_diff_rows = _build_repair_history_diff_rows
UniversalMainWindow.fill_repair_history_diff_table = _fill_repair_history_diff_table
UniversalMainWindow.compare_ai_repair_history_entry = _compare_ai_repair_history_entry
UniversalMainWindow.apply_ai_repair_history_entry = _apply_ai_repair_history_entry
UniversalMainWindow.selected_repair_diff_fields = _selected_repair_diff_fields
UniversalMainWindow.apply_repair_history_fields = _apply_repair_history_fields
UniversalMainWindow.apply_best_ai_repair_history = _apply_best_ai_repair_history
UniversalMainWindow.apply_selected_ai_repair_history = _apply_selected_ai_repair_history
UniversalMainWindow.compare_selected_ai_repair_history = _compare_selected_ai_repair_history
UniversalMainWindow.apply_selected_ai_repair_fields = _apply_selected_ai_repair_fields
UniversalMainWindow.export_ai_repair_history_to_file = _export_ai_repair_history_to_file
UniversalMainWindow.export_ai_call_logs = _export_ai_call_logs
UniversalMainWindow.export_ai_call_summary = _export_ai_call_summary
UniversalMainWindow.export_ai_repair_history = _export_ai_repair_history
UniversalMainWindow.clear_ai_call_logs_and_refresh = _clear_ai_call_logs_and_refresh
UniversalMainWindow.confirm_clear_ai_call_logs = _confirm_clear_ai_call_logs


def run_universal_app():
    app = QApplication.instance() or QApplication(sys.argv)
    window = UniversalMainWindow()
    window.show()
    return app.exec()


def pick_element_from_page(url, timeout_seconds=90):
    from playwright.sync_api import sync_playwright

    result_queue = queue.Queue(maxsize=1)
    script = """
    (() => {
      if (window.__collectorPickerInstalled) return;
      window.__collectorPickerInstalled = true;
      const style = document.createElement('style');
      style.textContent = `
        *[data-collector-hover="1"] { outline: 3px solid #1d4ed8 !important; cursor: crosshair !important; }
        #collector-picker-tip {
          position: fixed; left: 12px; top: 12px; z-index: 2147483647;
          background: #111827; color: white; padding: 8px 10px;
          font: 14px/1.4 sans-serif; border-radius: 6px;
        }
      `;
      document.documentElement.appendChild(style);
      const tip = document.createElement('div');
      tip.id = 'collector-picker-tip';
      tip.textContent = '点击要采集的文字、图片或链接；按 Esc 取消';
      document.body.appendChild(tip);
      let last = null;
      function selectorFor(el) {
        const tag = (el.tagName || '').toLowerCase();
        if (el.id) return `${tag}#${CSS.escape(el.id)}`;
        const classes = Array.from(el.classList || []).filter(Boolean).slice(0, 3);
        if (classes.length) return tag + classes.map(c => '.' + CSS.escape(c)).join('');
        const parent = el.parentElement;
        if (!parent) return tag;
        const siblings = Array.from(parent.children).filter(x => x.tagName === el.tagName);
        if (siblings.length > 1) return `${tag}:nth-of-type(${siblings.indexOf(el) + 1})`;
        return tag;
      }
      document.addEventListener('mouseover', event => {
        if (last) last.removeAttribute('data-collector-hover');
        last = event.target;
        if (last && last.id !== 'collector-picker-tip') last.setAttribute('data-collector-hover', '1');
      }, true);
      document.addEventListener('click', event => {
        event.preventDefault();
        event.stopPropagation();
        const el = event.target;
        window.__collectorPickResult = {
          tag: (el.tagName || '').toLowerCase(),
          id: el.id || '',
          classes: Array.from(el.classList || []),
          selector: selectorFor(el),
          text: (el.innerText || el.alt || el.title || '').trim().slice(0, 500)
        };
      }, true);
      document.addEventListener('keydown', event => {
        if (event.key === 'Escape') window.__collectorPickResult = {cancelled: true};
      }, true);
    })();
    """

    def run_picker():
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            page.evaluate(script)
            deadline = time.time() + timeout_seconds
            result = None
            while time.time() < deadline:
                result = page.evaluate("window.__collectorPickResult || null")
                if result:
                    break
                page.wait_for_timeout(250)
            browser.close()
            if result and not result.get("cancelled"):
                result_queue.put(result)
            else:
                result_queue.put(None)

    thread = threading.Thread(target=run_picker, daemon=True)
    thread.start()
    thread.join(timeout_seconds + 10)
    if thread.is_alive():
        raise RuntimeError("点选超时，请重新打开后点击目标元素。")
    return result_queue.get_nowait() if not result_queue.empty() else None


def run_universal_self_test():
    from universal_self_test import run_universal_self_test as _run_universal_self_test

    return _run_universal_self_test()
