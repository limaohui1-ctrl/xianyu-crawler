# Firecrawl Fusion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Firecrawl-compatible enhanced scraping engine to the desktop collector without copying the recovered Firecrawl monorepo into this Python app.

**Architecture:** Create a small local adapter inspired by the recovered Firecrawl Python SDK and v2 API (`scrape`, `map`, later `crawl/search/parse/interact`). The existing `UniversalCollector` remains the orchestration point; when Firecrawl is enabled it asks the remote/self-hosted Firecrawl-compatible API for markdown/html/links and maps the response into the existing record schema, falling back to the local browser/static collector on errors.

**Tech Stack:** Python standard library HTTP (`urllib`), PyQt6 desktop UI, existing SQLite record schema, recovered Firecrawl v2 API shape from `D:\爱马仕智能体\firecrawl-recovered\firecrawl-main`.

---

### Task 1: Firecrawl Adapter

**Files:**
- Create: `core_firecrawl.py`
- Test: `universal_self_test.py`

- [x] **Step 1: Write adapter conversion tests**

Add a self-test block that imports `FirecrawlClient`, `FirecrawlConfig`, and `firecrawl_document_to_record`. Use a fake transport returning:

```python
{
    "success": True,
    "data": {
        "markdown": "# Firecrawl 商品\n\n正文资料",
        "html": "<html><body><h1>Firecrawl 商品</h1><a href='/detail/2'>详情</a></body></html>",
        "links": [{"url": "https://example.com/detail/2", "text": "详情"}],
        "metadata": {"title": "Firecrawl 商品", "sourceURL": "https://example.com/item/1"},
    },
}
```

Assert the mapped record has `title == "Firecrawl 商品"`, `body` containing markdown, `links` containing `/detail/2`, and `template_name` containing `Firecrawl`.

- [x] **Step 2: Implement adapter**

Implement:

```python
class FirecrawlConfig:
    enabled: bool
    api_key: str
    base_url: str
    formats: list[str]
    only_main_content: bool
    use_map: bool
    map_limit: int
    timeout_seconds: int
```

Implement `FirecrawlClient.post_json(endpoint, payload)` using `urllib.request`, `Authorization: Bearer <key>`, JSON body, timeout, 502 retry once, and clear error messages. Implement `scrape(url, config)` and `map(url, config)`.

- [x] **Step 3: Implement record mapping**

Map Firecrawl documents to existing record fields:

```python
{
    "collected_at": now_text(),
    "url": metadata.sourceURL or metadata.url or fallback_url,
    "domain": url_domain(url),
    "template_name": f"{template_name} + Firecrawl",
    "title": metadata.title or first markdown heading,
    "body": markdown or html,
    "links": normalized Firecrawl links plus links parsed from html,
    "images": image URLs from metadata/html,
    "tables": [],
}
```

Call `assess_record_completeness()` and `content_fingerprint()`.

### Task 2: Collector Integration

**Files:**
- Modify: `universal_core.py`
- Modify: `ui_workers.py`

- [x] **Step 1: Extend `UniversalCollector.collect_urls()`**

Add optional `firecrawl_config=None`. If enabled, call a helper before local browser/static collection. The helper should:
- call `map()` first when `use_map` and `page_limit > 1` to expand target URLs;
- call `scrape()` for each target URL;
- save records through existing database flow;
- emit progress stages with `Firecrawl 映射`, `Firecrawl 采集`, `Firecrawl 完成`;
- on Firecrawl error, log diagnostics and continue local fallback.

- [x] **Step 2: Extend `CollectWorker`**

Add `firecrawl_config` to constructor, store it, and pass it into `collector.collect_urls()`.

### Task 3: UI Configuration

**Files:**
- Modify: `universal_ui.py`
- Test: `universal_self_test.py`

- [x] **Step 1: Add controls to advanced task tab**

In `build_task_tab()`, add:
- `self.firecrawl_enabled_checkbox = QCheckBox("启用 Firecrawl 增强")`
- `self.firecrawl_api_key_input = QLineEdit()` with password echo mode
- `self.firecrawl_base_url_input = QLineEdit("https://api.firecrawl.dev")`
- `self.firecrawl_map_checkbox = QCheckBox("用 Firecrawl Map 扩展分页/子链接")`

- [x] **Step 2: Add config methods**

Add `current_firecrawl_config()` returning a dict with `enabled`, `api_key`, `base_url`, `formats`, `only_main_content`, `use_map`, `map_limit`, and `timeout_seconds`. Pull API key from input or `FIRECRAWL_API_KEY`.

- [x] **Step 3: Wire runtime config**

Include `firecrawl` in `current_run_config()` and pass the dict to `CollectWorker`.

- [x] **Step 4: Self-test UI config**

In `universal_self_test.py`, assert the Firecrawl controls exist, setting them changes `current_firecrawl_config()`, and `current_run_config()` includes the Firecrawl config.

### Task 4: Verification

**Files:**
- Modify: `README.md`

- [x] **Step 1: Update verification docs**

Add `core_firecrawl.py` to the README compile command.

- [x] **Step 2: Run verification**

Run:

```powershell
python -m py_compile main.py universal_core.py core_firecrawl.py core_urls.py core_export.py core_database.py core_ai_storage.py universal_ui.py ui_workers.py universal_self_test.py universal_self_test_runtime.py ui_ai_settings.py ui_history.py ui_exports.py ui_queue.py ui_ai_history.py ui_export_utils.py tools/verify_repo_hygiene.py
python tools/verify_repo_hygiene.py
python main.py --self-test
python main.py --self-test --xianyu
python -m PyInstaller --noconfirm '通用网站采集中心.spec'
& 'D:\咸鱼爬取软件\dist\通用网站采集中心\通用网站采集中心.exe' --self-test
& 'D:\咸鱼爬取软件\dist\通用网站采集中心\通用网站采集中心.exe' --self-test --xianyu
```

- [ ] **Step 3: Commit**

Commit with Lore trailers explaining that this is the first Firecrawl fusion slice and that later slices should add `search`, `parse`, `crawl status`, and `interact` rather than vendoring the monorepo.

### Task 5: Firecrawl Search / Extract Fusion

**Files:**
- Modify: `core_firecrawl.py`
- Modify: `universal_core.py`
- Modify: `universal_ui.py`
- Test: `universal_self_test.py`

- [x] **Step 1: Add v2 Search support**

Implemented `FirecrawlClient.search()` for `/v2/search`, normalizing `web/news/images` result buckets into URL candidates.

- [x] **Step 2: Add v2 Extract support**

Implemented `start_extract()`, `get_extract_status()`, `extract()` polling, and `merge_firecrawl_extract_record()` to fold structured data into existing record body/table fields without changing the SQLite schema.

- [x] **Step 3: Wire Search and Extract into collector**

`UniversalCollector.collect_urls()` can now expand the URL queue through Firecrawl Search before crawling, and `collect_one_firecrawl()` can enrich scrape records with Extract output while keeping scrape results if Extract fails.

- [x] **Step 4: Wire Search and Extract into UI/run config**

Added advanced task controls for Search query/limit and Extract prompt. Task archives and schedules persist only safe config summaries, not Firecrawl API keys.

- [x] **Step 5: Verify Search and Extract**

Self-test now covers Search request/normalization, Extract polling/merge, UI config persistence, task archive reuse, schedule reuse, and collector Search/Map/Extract branch handoff.

### Task 6: Firecrawl Batch Scrape / Crawl Fusion

**Files:**
- Modify: `core_firecrawl.py`
- Modify: `universal_core.py`
- Modify: `universal_ui.py`
- Test: `universal_self_test.py`

- [x] **Step 1: Add v2 Batch Scrape support**

Implemented `start_batch_scrape()`, `get_batch_scrape_status()`, `batch_scrape()` polling, and normalized batch job payloads.

- [x] **Step 2: Add v2 Crawl support**

Implemented `start_crawl()`, `get_crawl_status()`, `crawl()` polling, crawl limits, max discovery depth, and same-record mapping as scrape documents.

- [x] **Step 3: Wire Batch and Crawl into collector**

`UniversalCollector.collect_urls()` can now use Firecrawl Batch for multi-URL remote scraping and Firecrawl Crawl for deep site discovery, with local fallback when a remote job fails or returns no documents.

- [x] **Step 4: Wire Batch and Crawl into UI/run config**

Added advanced task controls for Batch concurrency and Crawl page/depth limits. Task archives and schedules persist safe config summaries only.

- [x] **Step 5: Verify Batch and Crawl**

Self-test now covers Batch/Crawl request payloads, polling normalization, UI config persistence, schedule/run archive reuse, and collector branches that save Batch/Crawl returned documents.

### Task 7: Firecrawl Parse / Interact Fusion

**Files:**
- Modify: `core_firecrawl.py`
- Modify: `universal_core.py`
- Modify: `ui_workers.py`
- Modify: `universal_ui.py`
- Test: `universal_self_test.py`

- [x] **Step 1: Add v2 Parse support**

Implemented multipart upload for `/v2/parse` and `parse_file_to_table()` so the existing local file-to-table workflow can optionally use Firecrawl Parse before falling back to local/AI extraction.

- [x] **Step 2: Add v2 Interact support**

Implemented `/v2/scrape/:jobId/interact` execution and stop normalization. Scrape responses preserve a Firecrawl job id when available.

- [x] **Step 3: Wire Parse and Interact into workflows**

File extraction passes Firecrawl config through the worker. Page records can merge Interact output into body/table fields when a scrape-bound job id is available.

- [x] **Step 4: Wire Parse and Interact into UI/run config**

Added advanced task controls for Parse, Interact, wait time, and interaction prompt. Task archives and schedules persist safe config summaries only.

- [x] **Step 5: Verify Parse and Interact**

Self-test now covers multipart Parse, Interact execution normalization, record merge behavior, UI config persistence, schedule/run archive reuse, and collector Interact branch handoff.

### Task 8: Firecrawl Boundary Cleanup

**Files:**
- Create: `core_firecrawl_flow.py`
- Create: `ui_firecrawl.py`
- Modify: `universal_core.py`
- Modify: `universal_ui.py`
- Modify: `README.md`

- [x] **Step 1: Split collector-side Firecrawl orchestration**

Moved Map/Search/Scrape/Extract/Interact helper flow into `core_firecrawl_flow.py`. `UniversalCollector` keeps the old method names as thin wrappers so existing tests and extension points still work.

- [x] **Step 2: Split Firecrawl UI config**

Moved Firecrawl control construction, layout wiring, config serialization, config restore, and summary text helpers into `ui_firecrawl.py`.

- [x] **Step 3: Update verification docs**

Updated the README compile command and Firecrawl maintenance note to include the new boundary modules.

### Task 9: Firecrawl Crawl / Batch Flow Extraction

**Files:**
- Modify: `core_firecrawl_flow.py`
- Modify: `universal_core.py`

- [x] **Step 1: Move Crawl orchestration into the Firecrawl flow module**

Moved the Crawl loop, result persistence, progress updates, and fallback URL calculation into `collect_with_firecrawl_crawl()`.

- [x] **Step 2: Move Batch orchestration into the Firecrawl flow module**

Moved Batch URL de-duplication, remote batch scrape, result persistence, and fallback behavior into `collect_with_firecrawl_batch()`.

- [x] **Step 3: Keep collector extension points stable**

`UniversalCollector.collect_urls()` still calls `self.record_from_firecrawl_document()` and the existing wrapper methods remain available for tests and future overrides.

---

## Self-Review

Spec coverage:
- Firecrawl source was inspected through README, Python SDK, v2 methods, API routes, and API search/scrape/crawl/map references.
- This plan integrates the Firecrawl scrape/map capability into the current desktop collector and leaves the larger monorepo as an external reference.

Placeholder scan:
- No implementation placeholders are used; later Firecrawl capabilities are explicitly deferred to subsequent slices because they are separate subsystems.

Type consistency:
- `firecrawl_config` is a plain dict at UI/worker boundaries and normalized into `FirecrawlConfig` in `core_firecrawl.py`.
