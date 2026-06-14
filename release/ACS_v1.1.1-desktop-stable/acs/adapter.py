"""
Adapter — bridge between ACS (advanced crawler system) and the existing codebase.

This module provides compatibility wrappers that allow the new ACS modules
to interoperate with the existing UniversalCollector, UniversalExtractor,
and other legacy components WITHOUT modifying them.

Usage:
    from acs.adapter import (
        parse_with_acs_engine,          # Use ACS multi-parser instead of UniversalExtractor
        dedup_with_acs_store,            # Use ACS DedupStore with existing URL dedup
        checkpoint_with_acs,             # Use ACS CheckpointManager alongside existing one
        convert_legacy_record,           # Convert legacy dict to ACS ParseResult
        convert_to_legacy_record,        # Convert ACS ParseResult to legacy dict
        create_acs_logger,               # Create an ACS CrawlLogger from existing config
    )
"""

from typing import Any, Callable, Dict, List, Optional, Tuple
import sys
import os
import json
import time

# ACS_MODE: off|shadow|on  (default: shadow)
#   off    — 完全关闭 ACS，使用旧流程
#   shadow — 旁路对比模式：ACS 在后台运行解析，结果写入 JSONL 日志，旧流程作为正式输出
#   on     — ACS 输出作为正式结果，旧流程作为 fallback
ACS_MODE = os.environ.get("ACS_MODE", "shadow").lower()
if ACS_MODE not in ("off", "shadow", "on"):
    ACS_MODE = "shadow"

# Ensure project root is on path for legacy imports
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from acs.core.result_model import ParseResult, PageImage, PageLink, PageTable
from acs.core.task_model import Task, TaskConfig, TaskStatus, FetchMode, ParseMode
from acs.core.error_model import ErrorRecord, ErrorLog, ErrorCategory, ErrorSeverity
from acs.parser.parser_engine import ParserEngine
from acs.schema.normalizer import normalize_result
from acs.schema.validator import validate_result
from acs.schema.quality_score import score_quality
from acs.storage.dedup import DedupStore, normalize_url_for_dedup, content_dedup_key
from acs.storage.checkpoint import CheckpointManager
from acs.storage.export_json import JsonExporter, ExportConfig
from acs.observability.logger import CrawlLogger, get_logger


# ── Engine singleton ──────────────────────────────────────────────

_engine: Optional[ParserEngine] = None


def get_acs_engine() -> ParserEngine:
    """Get or create the singleton ACS parser engine."""
    global _engine
    if _engine is None:
        _engine = ParserEngine.create_default()
    return _engine


# ── Parsing adapter ───────────────────────────────────────────────

def parse_with_acs_engine(url: str, html: str, http_status: int = 200,
                          mime_type: str = "text/html") -> ParseResult:
    """Use the ACS multi-parser engine to extract data from HTML.

    This is a drop-in replacement for UniversalExtractor.extract(html, url)
    that returns an ACS ParseResult instead of a legacy dict.
    """
    engine = get_acs_engine()
    result, attempts = engine.parse(url, html, http_status=http_status, mime_type=mime_type)
    return result


# ── ACS shadow / main-flow integration ────────────────────────────

def _acs_shadow_log_dir() -> str:
    """Return the directory for ACS shadow comparison logs."""
    base = os.environ.get("UNIVERSAL_COLLECTOR_DATA_DIR",
                          os.path.join(_PROJECT_ROOT, "acs_shadow_logs"))
    return os.path.abspath(base)


def acs_shadow_collect(url: str, html: str, legacy_record: dict,
                       fetch_quality: str = "full",
                       log_func=None) -> Optional[dict]:
    """Run ACS parser in shadow (or active) mode alongside the legacy flow.

    This is the single integration point for ACS into the main crawl loop.
    Called from UniversalCollector.collect_one() after the legacy extract.

    Modes (controlled by ACS_MODE env var, default "shadow"):
      - "off":     returns None immediately (ACS disabled)
      - "shadow":  runs ACS parser, logs comparison, returns None (legacy output used)
      - "on":      runs ACS parser, returns ACS result as legacy dict on success;
                   falls back to legacy_result on failure

    Args:
        url: Source URL
        html: Fetched HTML content
        legacy_record: The record dict produced by UniversalExtractor.extract()
        fetch_quality: Quality label from the fetch step
        log_func: Optional callable for logging (e.g. self.log)

    Returns:
        - None for "off" / "shadow" modes (legacy record is the official output)
        - legacy-format dict for "on" mode (ACS output, with legacy fallback)
    """
    if ACS_MODE == "off":
        return None

    # ── Run ACS parser ──
    acs_result = None
    acs_error = ""
    try:
        acs_result = parse_with_acs_engine(url, html)
        normalize_result(acs_result)
    except Exception as exc:
        acs_error = str(exc)[:500]

    # ── Build comparison data ──
    shadow_entry = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "url": url,
        "mode": ACS_MODE,
        "legacy_title": legacy_record.get("title", "")[:100],
        "legacy_body_len": len(legacy_record.get("body", "") or ""),
        "legacy_error": legacy_record.get("error", "")[:200],
        "acs_success": acs_result is not None and not acs_error,
        "acs_parser": acs_result.parser_used if acs_result else "",
        "acs_title": acs_result.title[:100] if acs_result else "",
        "acs_body_len": len(acs_result.body) if acs_result else 0,
        "acs_quality": acs_result.quality_label if acs_result else "",
        "acs_completeness": acs_result.completeness if acs_result else 0,
        "acs_error": acs_error[:200],
    }

    # ── Write to shadow log ──
    try:
        log_dir = _acs_shadow_log_dir()
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "acs_shadow.jsonl")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(shadow_entry, ensure_ascii=False) + "\n")
    except OSError:
        pass

    # ── Log to console if log_func provided ──
    if log_func and acs_result:
        log_func(f"[ACS shadow] parser={acs_result.parser_used} "
                 f"quality={acs_result.quality_label} "
                 f"completeness={acs_result.completeness}% "
                 f"title={acs_result.title[:40]}")
    elif log_func and acs_error:
        log_func(f"[ACS shadow] FAILED: {acs_error[:100]}")

    # ── Mode decision ──
    if ACS_MODE == "on":
        if acs_result and not acs_error:
            return convert_to_legacy_record(acs_result)
        else:
            # Fall back to legacy
            if log_func:
                log_func(f"[ACS on] ACS 解析失败，回退到旧流程: {acs_error[:80]}")
            return None  # caller should use legacy_record

    # shadow mode: always return None (legacy output is official)
    return None


# ── Record conversion ─────────────────────────────────────────────

def convert_legacy_record(legacy: dict) -> ParseResult:
    """Convert a legacy record dict (from UniversalExtractor) to an ACS ParseResult."""
    result = ParseResult(
        url=str(legacy.get("url", "")),
        parsed_at=str(legacy.get("collected_at", "")),
        domain=str(legacy.get("domain", "")),
        template_name=str(legacy.get("template_name", "auto")),
        title=str(legacy.get("title", "")),
        price=str(legacy.get("price", "")),
        published_time=str(legacy.get("published_time", "")),
        author=str(legacy.get("author", "")),
        body=str(legacy.get("body", "")),
        parser_used="legacy",
        fetch_quality=str(legacy.get("fetch_quality", "full")),
        error=str(legacy.get("error", "")),
    )

    # Images
    images = legacy.get("images", [])
    if isinstance(images, str):
        images = [i.strip() for i in images.split("\n") if i.strip()]
    result.images = images[:120]

    # Links
    links = legacy.get("links", [])
    if isinstance(links, str):
        links = [l.strip() for l in links.split("\n") if l.strip()]
    result.links = links[:300]

    # Tables
    tables = legacy.get("tables", [])
    if isinstance(tables, str):
        tables = [tables]
    result.tables = tables[:200]

    # Fingerprint
    fp = legacy.get("fingerprint", "")
    if fp:
        result.content_hash = str(fp)

    # Completeness
    result.completeness = int(legacy.get("completeness_score", 0))
    result.quality_label = str(legacy.get("completeness_label", "low"))
    result.missing_fields = legacy.get("completeness_missing", [])

    if not result.content_hash:
        result.build()
    return result


def convert_to_legacy_record(result: ParseResult) -> dict:
    """Convert an ACS ParseResult back to the legacy dict format expected by the
    existing database and export code."""
    return {
        "collected_at": result.parsed_at,
        "url": result.url,
        "domain": result.domain,
        "template_name": result.template_name,
        "title": result.title,
        "price": result.price,
        "published_time": result.published_time,
        "author": result.author,
        "body": result.body,
        "images": result.images,
        "links": result.links,
        "tables": result.tables,
        "error": result.error,
        "fetch_quality": result.fetch_quality,
        "fingerprint": result.content_hash,
        "completeness_score": result.completeness,
        "completeness_label": result.quality_label,
        "completeness_missing": result.missing_fields,
        "completeness_summary": f"ACS: {result.parser_used} | {result.quality_label}",
    }


# ── Dedup adapter ─────────────────────────────────────────────────

_dedup_store: Optional[DedupStore] = None


def get_acs_dedup_store() -> DedupStore:
    """Get or create the singleton ACS dedup store."""
    global _dedup_store
    if _dedup_store is None:
        _dedup_store = DedupStore()
    return _dedup_store


def dedup_with_acs_store(url: str, result: Optional[ParseResult] = None) -> Tuple[bool, str]:
    """Check if a URL or its content is a duplicate.

    Returns (is_duplicate, reason).
      - is_duplicate=True: should skip this URL/content
      - is_duplicate=False: safe to process, already marked as seen

    Args:
        url: The URL to check
        result: Optional ParseResult for content-level dedup

    """
    store = get_acs_dedup_store()

    # Check URL dedup first
    if store.is_url_duplicate(url):
        store.mark_url_duplicate(url)
        return True, "url_duplicate"

    # Check content dedup
    if result and store.is_content_duplicate(result):
        store.mark_content_duplicate(result)
        return True, "content_duplicate"

    # Mark as seen
    store.mark_url(url)
    if result:
        store.mark_content(result)

    return False, ""


# ── Checkpoint adapter ────────────────────────────────────────────

def checkpoint_with_acs(checkpoint_dir: str, run_id: str,
                        urls: List[str], config: Optional[dict] = None,
                        save_interval: int = 10) -> CheckpointManager:
    """Create an ACS CheckpointManager for a run.

    Can be used alongside the existing core_checkpoint.CheckpointManager
    (they don't interfere — different storage backends).
    """
    mgr = CheckpointManager(
        checkpoint_dir=checkpoint_dir,
        run_id=run_id,
        save_interval=save_interval,
    )
    mgr.init(urls, config=config)
    return mgr


# ── Logger adapter ────────────────────────────────────────────────

def create_acs_logger(name: str = "crawler", log_dir: Optional[str] = None) -> CrawlLogger:
    """Create an ACS CrawlLogger, optionally with file output."""
    log_file = None
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"{name}.jsonl")
    return get_logger(name=name, log_file=log_file)


# ── Task conversion ───────────────────────────────────────────────

def task_from_legacy_params(url: str, template_name: str = "auto",
                            use_browser: bool = False,
                            scroll_times: int = 0,
                            timeout: int = 30,
                            max_retries: int = 3) -> Task:
    """Create an ACS Task from legacy UniversalCollector parameters."""
    return Task(
        url=url,
        template_name=template_name,
        config=TaskConfig(
            fetch_mode=FetchMode.BROWSER if use_browser else FetchMode.STATIC,
            parse_mode=ParseMode.AUTO,
            timeout_seconds=timeout,
            max_retries=max_retries,
            scroll_times=scroll_times,
        ),
    )


# ── Self-consistency check ────────────────────────────────────────

def run_integration_smoke_test() -> dict:
    """Run a quick smoke test to verify ACS modules are importable and functional.

    Returns a dict with test results.
    """
    results = {}

    # 1. Verify all core modules import
    try:
        from acs.core import task_model, result_model, error_model
        results["core_models"] = "pass"
    except Exception as e:
        results["core_models"] = f"fail: {e}"

    # 2. Verify parser engine works end-to-end
    try:
        result = parse_with_acs_engine(
            "http://example.com",
            "<!DOCTYPE html><html><head><title>Smoke Test</title></head><body><p>Hello ACS</p></body></html>"
        )
        if result.title == "Smoke Test" and "Hello ACS" in result.body:
            results["parser_engine"] = "pass"
        else:
            results["parser_engine"] = f"fail: unexpected output (title={result.title}, body_len={len(result.body)})"
    except Exception as e:
        results["parser_engine"] = f"fail: {e}"

    # 3. Verify dedup works (use the SAME singleton as dedup_with_acs_store)
    try:
        store = get_acs_dedup_store()
        store.mark_url("http://test.com/page")
        is_dup, reason = dedup_with_acs_store("http://test.com/page")
        if is_dup and reason == "url_duplicate":
            results["dedup"] = "pass"
        else:
            results["dedup"] = f"fail: unexpected (dup={is_dup}, reason={reason})"
    except Exception as e:
        results["dedup"] = f"fail: {e}"

    # 4. Verify checkpoint works
    try:
        import tempfile, shutil
        d = tempfile.mkdtemp()
        try:
            mgr = checkpoint_with_acs(d, "smoke_test", ["http://a.com", "http://b.com"])
            mgr.record_progress("http://a.com")
            mgr.record_progress("http://b.com")
            mgr.mark_completed()
            state = mgr.load_latest()
            if state and state.status == "completed":
                results["checkpoint"] = "pass"
            else:
                results["checkpoint"] = f"fail: state status={state.status if state else None}"
        finally:
            shutil.rmtree(d, ignore_errors=True)
    except Exception as e:
        results["checkpoint"] = f"fail: {e}"

    # 5. Verify schema works
    try:
        result = ParseResult(url="http://x.com", title="T", body="B")
        result.build()
        normalized = normalize_result(result)
        report = validate_result(normalized)
        qs = score_quality(normalized)
        if report.valid and qs.total >= 0:
            results["schema"] = "pass"
        else:
            results["schema"] = f"fail: valid={report.valid}, quality={qs.total}"
    except Exception as e:
        results["schema"] = f"fail: {e}"

    # 6. Verify error model
    try:
        err = ErrorRecord.from_exception("http://x.com", ConnectionError("Connection refused"), task_id="t1")
        if err.category in (ErrorCategory.NETWORK_REFUSED, ErrorCategory.NETWORK_GENERAL):
            results["error_model"] = "pass"
        else:
            results["error_model"] = f"fail: category={err.category}"
    except Exception as e:
        results["error_model"] = f"fail: {e}"

    # 7. Verify export
    try:
        import tempfile, shutil
        d = tempfile.mkdtemp()
        try:
            r = ParseResult(url="http://x.com", title="Export Test", body="Content", parser_used="css")
            r.build()
            exporter = JsonExporter(ExportConfig(output_dir=d, format="jsonl", pretty=False))
            path = exporter.export([r], filename="smoke_export")
            if os.path.exists(path) and os.path.getsize(path) > 0:
                results["export"] = "pass"
            else:
                results["export"] = "fail: file missing or empty"
        finally:
            shutil.rmtree(d, ignore_errors=True)
    except Exception as e:
        results["export"] = f"fail: {e}"

    # Aggregate
    all_pass = all(v == "pass" for v in results.values())
    results["overall"] = "pass" if all_pass else "fail"
    return results


if __name__ == "__main__":
    import json
    report = run_integration_smoke_test()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report.get("overall") != "pass":
        sys.exit(1)
