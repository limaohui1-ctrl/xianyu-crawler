# Project Context — 通用网站采集中心

## What this is
A Windows desktop web scraper/crawler for non-technical users. PyQt6 GUI.
Core features: intelligent web page collection + AI-powered field extraction + scheduled monitoring + template management + Excel/CSV/JSON export.

## Architecture
```
main.py                    # Entry point: app, self-test, legacy xianyu launcher
universal_core.py          # Core business logic (collectors, AI settings, URL normalization)
universal_ui.py            # Main UI window (~7600 lines, being split)
core_ai_client.py          # AIClient class (extracted from universal_core.py)
core_ai_storage.py         # DPAPI encryption, JSONL log storage
core_database.py           # SQLite persistence, change tracking
core_export.py             # Export helpers (XLSX, CSV, JSON, TSV)
core_urls.py               # URL normalization and parsing
core_firecrawl.py          # Firecrawl API client
core_firecrawl_flow.py     # Firecrawl collection orchestration
core_nl_web_crawler.py     # Natural-language web crawling

ui_*.py                    # 41+ UI sub-modules injected via @register decorator
ui_registry.py             # Decorator registry that binds methods to UniversalMainWindow
universal_self_test.py     # Comprehensive regression test suite (14 stages)
```

## Key patterns
- **@register decorator**: UI methods are defined in `ui_*.py` modules and auto-bound to `UniversalMainWindow` via `ui_registry.py`. No manual import renaming needed.
- **Atomic file writes**: Config/JSON saves use `.tmp` + `os.replace()` to prevent corruption.
- **DPAPI encryption**: API keys encrypted with Windows Data Protection API (`core_ai_storage.py`).
- **JSONL logging**: AI call logs and repair history are append-only JSONL with file locks.

## Dev workflow
```bash
# 1. Compile check
python -m py_compile main.py universal_core.py universal_ui.py

# 2. Repo hygiene
python tools/verify_repo_hygiene.py

# 3. Run self-test (14 stages, ~60s)
python main.py --self-test

# 4. Package
python -m PyInstaller --noconfirm 通用网站采集中心.spec
powershell -NoProfile -ExecutionPolicy Bypass -File build_release.ps1
```

## Common pitfalls
- Chinese-path repos: use `cmd //c "cd /d D:\... && ..."` from bash
- Universal test exits quickly — check `self_test_runtime/latest_universal_self_test.json`
- When adding new UI modules: add `@register("method_name")`, import in universal_ui.py, add to .spec hiddenimports
- self-test monkeypatches `start_collecting` — check those lambdas before modifying collect flow
- `.gitignore` MUST cover all generated runtime artifacts — run verify_repo_hygiene.py before commits

## Known issues (see CHANGELOG.md)
- Memory palace: preview-only, full implementation pending
- universal_ui.py: still needs further splitting
