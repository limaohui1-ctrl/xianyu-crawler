"""Firecrawl UI controls and config helpers."""

from ui_registry import register

import os

from PyQt6.QtWidgets import QCheckBox, QLabel, QLineEdit, QSpinBox

from core_firecrawl import FIRECRAWL_DEFAULT_BASE_URL


FIRECRAWL_DEFAULT_BASE_URL = "https://api.firecrawl.dev"


def build_firecrawl_controls(owner):
    owner.firecrawl_enabled_checkbox = QCheckBox("启用 Firecrawl 增强")
    owner.firecrawl_api_key_input = QLineEdit()
    owner.firecrawl_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
    owner.firecrawl_api_key_input.setPlaceholderText("fc-...；自托管无鉴权可留空")
    owner.firecrawl_base_url_input = QLineEdit(FIRECRAWL_DEFAULT_BASE_URL)

    owner.firecrawl_map_checkbox = QCheckBox("用 Firecrawl Map 扩展链接")
    owner.firecrawl_map_checkbox.setChecked(True)
    owner.firecrawl_search_checkbox = QCheckBox("用 Firecrawl Search 扩源")
    owner.firecrawl_search_query_input = QLineEdit()
    owner.firecrawl_search_query_input.setPlaceholderText("搜索关键词，留空则不扩源")
    owner.firecrawl_search_limit_input = QSpinBox()
    owner.firecrawl_search_limit_input.setRange(1, 100)
    owner.firecrawl_search_limit_input.setValue(5)

    owner.firecrawl_extract_checkbox = QCheckBox("用 Firecrawl Extract 结构化")
    owner.firecrawl_extract_prompt_input = QLineEdit()
    owner.firecrawl_extract_prompt_input.setPlaceholderText("抽取要求，例如：提取标题、价格、作者、时间、规格")

    owner.firecrawl_batch_checkbox = QCheckBox("用 Firecrawl Batch 批量抓")
    owner.firecrawl_batch_concurrency_input = QSpinBox()
    owner.firecrawl_batch_concurrency_input.setRange(1, 50)
    owner.firecrawl_batch_concurrency_input.setValue(5)

    owner.firecrawl_crawl_checkbox = QCheckBox("用 Firecrawl Crawl 深抓站点")
    owner.firecrawl_crawl_limit_input = QSpinBox()
    owner.firecrawl_crawl_limit_input.setRange(1, 1000)
    owner.firecrawl_crawl_limit_input.setValue(10)
    owner.firecrawl_crawl_depth_input = QSpinBox()
    owner.firecrawl_crawl_depth_input.setRange(1, 20)
    owner.firecrawl_crawl_depth_input.setValue(2)

    owner.firecrawl_parse_checkbox = QCheckBox("用 Firecrawl Parse 解析文件")
    owner.firecrawl_interact_checkbox = QCheckBox("用 Firecrawl Interact 交互")
    owner.firecrawl_interact_wait_input = QSpinBox()
    owner.firecrawl_interact_wait_input.setRange(0, 60000)
    owner.firecrawl_interact_wait_input.setValue(0)
    owner.firecrawl_interact_wait_input.setSuffix(" ms")
    owner.firecrawl_interact_prompt_input = QLineEdit()
    owner.firecrawl_interact_prompt_input.setPlaceholderText("交互提示，例如：点击展开更多后提取页面内容")


def add_firecrawl_controls_to_task_layout(owner, task_layout, auto_fix_button):
    task_layout.addWidget(owner.firecrawl_enabled_checkbox, 7, 0)
    task_layout.addWidget(QLabel("Firecrawl Key"), 7, 1)
    task_layout.addWidget(owner.firecrawl_api_key_input, 7, 2)
    task_layout.addWidget(auto_fix_button, 7, 3)
    task_layout.addWidget(owner.firecrawl_map_checkbox, 8, 0)
    task_layout.addWidget(QLabel("Firecrawl API"), 8, 1)
    task_layout.addWidget(owner.firecrawl_base_url_input, 8, 2, 1, 2)
    task_layout.addWidget(owner.firecrawl_search_checkbox, 9, 0)
    task_layout.addWidget(QLabel("Search 词"), 9, 1)
    task_layout.addWidget(owner.firecrawl_search_query_input, 9, 2)
    task_layout.addWidget(owner.firecrawl_search_limit_input, 9, 3)
    task_layout.addWidget(owner.firecrawl_extract_checkbox, 10, 0)
    task_layout.addWidget(QLabel("Extract 要求"), 10, 1)
    task_layout.addWidget(owner.firecrawl_extract_prompt_input, 10, 2, 1, 2)
    task_layout.addWidget(owner.firecrawl_batch_checkbox, 11, 0)
    task_layout.addWidget(QLabel("Batch 并发"), 11, 1)
    task_layout.addWidget(owner.firecrawl_batch_concurrency_input, 11, 2)
    task_layout.addWidget(owner.firecrawl_crawl_checkbox, 12, 0)
    task_layout.addWidget(QLabel("Crawl 页数/深度"), 12, 1)
    task_layout.addWidget(owner.firecrawl_crawl_limit_input, 12, 2)
    task_layout.addWidget(owner.firecrawl_crawl_depth_input, 12, 3)
    task_layout.addWidget(owner.firecrawl_parse_checkbox, 13, 0)
    task_layout.addWidget(owner.firecrawl_interact_checkbox, 13, 1)
    task_layout.addWidget(QLabel("Interact 等待"), 13, 2)
    task_layout.addWidget(owner.firecrawl_interact_wait_input, 13, 3)
    task_layout.addWidget(QLabel("Interact 提示"), 14, 0)
    task_layout.addWidget(owner.firecrawl_interact_prompt_input, 14, 1, 1, 3)


def _bounded_int(value, default, minimum, maximum):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def current_firecrawl_config(owner, include_secret=True, runtime_overrides=None, mask_api_key_func=None):
    runtime_overrides = runtime_overrides or {}
    source = dict(runtime_overrides.get("firecrawl") or {})
    enabled = bool(source.get("enabled", owner.firecrawl_enabled_checkbox.isChecked()))
    api_key = str(
        source.get("api_key")
        or owner.firecrawl_api_key_input.text().strip()
        or os.environ.get("FIRECRAWL_API_KEY", "")
    ).strip()
    base_url = str(source.get("base_url") or owner.firecrawl_base_url_input.text().strip() or FIRECRAWL_DEFAULT_BASE_URL).strip()
    map_limit = source.get("map_limit") or max(owner.page_limit_input.value(), owner.subpage_limit_input.value(), 1)

    config = {
        "enabled": enabled,
        "base_url": base_url,
        "formats": source.get("formats") or ["markdown", "html", "links"],
        "only_main_content": bool(source.get("only_main_content", True)),
        "use_map": bool(source.get("use_map", owner.firecrawl_map_checkbox.isChecked())),
        "map_limit": _bounded_int(map_limit, 1, 1, 1000),
        "use_search": bool(source.get("use_search", owner.firecrawl_search_checkbox.isChecked())),
        "search_query": str(source.get("search_query") or owner.firecrawl_search_query_input.text().strip()).strip(),
        "search_limit": _bounded_int(source.get("search_limit") or owner.firecrawl_search_limit_input.value(), 5, 1, 100),
        "search_sources": source.get("search_sources") or ["web"],
        "use_extract": bool(source.get("use_extract", owner.firecrawl_extract_checkbox.isChecked())),
        "extract_prompt": str(source.get("extract_prompt") or owner.firecrawl_extract_prompt_input.text().strip()).strip(),
        "extract_schema": source.get("extract_schema") or {},
        "extract_enable_web_search": bool(source.get("extract_enable_web_search", False)),
        "extract_poll_interval": _bounded_int(source.get("extract_poll_interval") or 2, 2, 1, 30),
        "extract_timeout_seconds": _bounded_int(source.get("extract_timeout_seconds") or 60, 60, 5, 600),
        "use_batch": bool(source.get("use_batch", owner.firecrawl_batch_checkbox.isChecked())),
        "batch_max_concurrency": _bounded_int(
            source.get("batch_max_concurrency") or owner.firecrawl_batch_concurrency_input.value(),
            5,
            1,
            50,
        ),
        "batch_poll_interval": _bounded_int(source.get("batch_poll_interval") or 2, 2, 1, 30),
        "batch_timeout_seconds": _bounded_int(source.get("batch_timeout_seconds") or 120, 120, 5, 1800),
        "use_crawl": bool(source.get("use_crawl", owner.firecrawl_crawl_checkbox.isChecked())),
        "crawl_limit": _bounded_int(source.get("crawl_limit") or owner.firecrawl_crawl_limit_input.value(), 10, 1, 1000),
        "crawl_max_depth": _bounded_int(source.get("crawl_max_depth") or owner.firecrawl_crawl_depth_input.value(), 2, 1, 20),
        "crawl_allow_external_links": bool(source.get("crawl_allow_external_links", False)),
        "crawl_poll_interval": _bounded_int(source.get("crawl_poll_interval") or 2, 2, 1, 30),
        "crawl_timeout_seconds": _bounded_int(source.get("crawl_timeout_seconds") or 180, 180, 5, 3600),
        "use_parse": bool(source.get("use_parse", owner.firecrawl_parse_checkbox.isChecked())),
        "use_interact": bool(source.get("use_interact", owner.firecrawl_interact_checkbox.isChecked())),
        "interact_prompt": str(source.get("interact_prompt") or owner.firecrawl_interact_prompt_input.text().strip()).strip(),
        "interact_language": source.get("interact_language") or "node",
        "interact_timeout_seconds": _bounded_int(source.get("interact_timeout_seconds") or 60, 60, 1, 300),
        "interact_wait_ms": _bounded_int(
            source.get("interact_wait_ms") or owner.firecrawl_interact_wait_input.value(),
            0,
            0,
            60000,
        ),
        "timeout_seconds": _bounded_int(source.get("timeout_seconds") or 45, 45, 5, 300),
    }
    if include_secret:
        config["api_key"] = api_key
    else:
        config["api_key_present"] = bool(api_key)
        config["api_key_preview"] = mask_api_key_func(api_key) if api_key and mask_api_key_func else ""
    return config


@register("apply_firecrawl_config_to_ui")
def apply_firecrawl_config_to_ui(owner, config):
    config = dict(config or {})
    if not config:
        return
    owner.firecrawl_enabled_checkbox.setChecked(bool(config.get("enabled", False)))
    owner.firecrawl_base_url_input.setText(str(config.get("base_url") or FIRECRAWL_DEFAULT_BASE_URL))
    owner.firecrawl_map_checkbox.setChecked(bool(config.get("use_map", True)))
    owner.firecrawl_search_checkbox.setChecked(bool(config.get("use_search", False)))
    owner.firecrawl_search_query_input.setText(str(config.get("search_query") or ""))
    owner.firecrawl_search_limit_input.setValue(_bounded_int(config.get("search_limit") or 5, 5, 1, 100))
    owner.firecrawl_extract_checkbox.setChecked(bool(config.get("use_extract", False)))
    owner.firecrawl_extract_prompt_input.setText(str(config.get("extract_prompt") or ""))
    owner.firecrawl_batch_checkbox.setChecked(bool(config.get("use_batch", False)))
    owner.firecrawl_batch_concurrency_input.setValue(_bounded_int(config.get("batch_max_concurrency") or 5, 5, 1, 50))
    owner.firecrawl_crawl_checkbox.setChecked(bool(config.get("use_crawl", False)))
    owner.firecrawl_crawl_limit_input.setValue(_bounded_int(config.get("crawl_limit") or 10, 10, 1, 1000))
    owner.firecrawl_crawl_depth_input.setValue(_bounded_int(config.get("crawl_max_depth") or 2, 2, 1, 20))
    owner.firecrawl_parse_checkbox.setChecked(bool(config.get("use_parse", False)))
    owner.firecrawl_interact_checkbox.setChecked(bool(config.get("use_interact", False)))
    owner.firecrawl_interact_wait_input.setValue(_bounded_int(config.get("interact_wait_ms") or 0, 0, 0, 60000))
    owner.firecrawl_interact_prompt_input.setText(str(config.get("interact_prompt") or ""))
    if config.get("api_key"):
        owner.firecrawl_api_key_input.setText(str(config.get("api_key") or ""))


def firecrawl_start_log_line(config):
    if not config or not config.get("enabled"):
        return ""
    key_text = "已配置 Key" if config.get("api_key") else "未配置 Key"
    return (
        f"Firecrawl 增强：{key_text}，API={config.get('base_url', '')}，"
        f"Search={'开' if config.get('use_search') else '关'}，"
        f"Extract={'开' if config.get('use_extract') else '关'}，"
        f"Batch={'开' if config.get('use_batch') else '关'}，"
        f"Crawl={'开' if config.get('use_crawl') else '关'}，"
        f"Parse={'开' if config.get('use_parse') else '关'}，"
        f"Interact={'开' if config.get('use_interact') else '关'}"
    )


def firecrawl_summary_line(config):
    if not config:
        return ""
    key_state = "已配置 Key" if config.get("api_key_present") else "未配置 Key"
    return (
        f"Firecrawl：{'开启' if config.get('enabled') else '关闭'}，"
        f"{key_state}，Map {'开启' if config.get('use_map') else '关闭'}，"
        f"Search {'开启' if config.get('use_search') else '关闭'}，"
        f"Extract {'开启' if config.get('use_extract') else '关闭'}，"
        f"Batch {'开启' if config.get('use_batch') else '关闭'}，"
        f"Crawl {'开启' if config.get('use_crawl') else '关闭'}，"
        f"Parse {'开启' if config.get('use_parse') else '关闭'}，"
        f"Interact {'开启' if config.get('use_interact') else '关闭'}，"
        f"API {config.get('base_url', '')}"
    )
