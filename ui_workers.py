"""Qt worker classes used by the desktop UI."""

import asyncio
import os
import time
import traceback

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from universal_core import (
    AIClient,
    UniversalCollector,
    WebAgentExecutor,
    ai_extract_file_to_table,
    ai_parse_task,
    ai_repair_fields,
    ai_suggest_fields,
    ai_transform_records,
    append_ai_call_log,
    compact_text,
    diagnose_ai_settings,
    download_images_from_records,
    mask_api_key,
    refresh_ai_provider_models,
    test_ai_provider_connectivity,
)
from core_nl_web_crawler import crawl_from_natural_language
from ui_export_utils import export_default_dir


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
        follow_link_content=False,
        follow_link_limit=0,
        follow_same_site=True,
        filter_pdf_media_links=False,
        run_id=0,
        firecrawl_config=None,
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
        self.follow_link_content = bool(follow_link_content)
        self.follow_link_limit = int(follow_link_limit or 0)
        self.follow_same_site = bool(follow_same_site)
        self.filter_pdf_media_links = bool(filter_pdf_media_links)
        self.run_id = int(run_id or 0)
        self.firecrawl_config = dict(firecrawl_config or {})
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
                if not saved_record.get("duplicate"):
                    self.emit_record_once(saved_record)
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
                firecrawl_config=self.firecrawl_config,
            )
            for record in results:
                if self.follow_link_content and not record.get("follow_link_content"):
                    record["follow_link_content"] = True
                    record["follow_link_limit"] = self.follow_link_limit
                    record["follow_same_site"] = self.follow_same_site
                    record["filter_pdf_media_links"] = self.filter_pdf_media_links
                    if not self.filter_pdf_media_links and str(record.get("url", "")).lower().endswith(".pdf"):
                        record["source_kind"] = "pdf_document"
            total_count = len(results)
            for record in results:
                if self.emit_record_once(record):
                    emitted_count += 1
            emitted_count = len(self._emitted_record_keys)
            if total_count:
                failed_total = sum(1 for item in results if item.get("error"))
                self.progress_signal.emit(
                    {
                        "processed": total_count,
                        "success": total_count - failed_total,
                        "failed": failed_total,
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
                self.payload.get("firecrawl_config", {}),
            )
        if self.action == "natural_language_web_crawl":
            return asyncio.run(
                crawl_from_natural_language(
                    self.payload.get("prompt", ""),
                    llm_base_url=settings.get("base_url", ""),
                    llm_api_key=settings.get("api_key", ""),
                    llm_model=settings.get("model", ""),
                    search_provider=self.payload.get("search_provider") or settings.get("search_provider") or os.getenv("NL_CRAWLER_SEARCH_PROVIDER") or "serper",
                    search_api_key=self.payload.get("search_api_key") or settings.get("search_api_key") or os.getenv("NL_CRAWLER_SEARCH_API_KEY") or "",
                    search_endpoint=self.payload.get("search_endpoint") or settings.get("search_endpoint") or os.getenv("NL_CRAWLER_SEARCH_ENDPOINT") or "",
                    timeout_seconds=float(self.payload.get("timeout_seconds") or 20.0),
                    page_timeout_seconds=float(self.payload.get("page_timeout_seconds") or 12.0),
                    max_search_results=int(self.payload.get("max_search_results") or 5),
                    demo_mode=bool(self.payload.get("demo_mode", False)),
                )
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
