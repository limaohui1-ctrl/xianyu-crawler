import base64
import hashlib
import json
import mimetypes
import os
import re
import shutil
import time
from copy import deepcopy
from dataclasses import dataclass, field
from html import unescape
from typing import Callable, Iterable, Optional
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from bs4 import BeautifulSoup

from core_export import (
    FIELD_DESCRIPTIONS,
    FIELD_HEADERS,
    export_records,
    export_table_data,
    records_to_tsv,
    safe_export_cell,
    table_data_to_tsv,
)
from core_database import (
    CollectorDatabase as _CoreCollectorDatabase,
    compare_records,
    content_fingerprint,
    row_to_record,
    row_to_run,
    safe_json,
)
from core_ai_storage import (
    clear_jsonl_file,
    decrypt_ai_settings_from_disk,
    encrypt_ai_settings_for_disk,
    append_jsonl_entry,
    load_jsonl_entries,
    protect_secret,
    summarize_ai_call_log_rows,
    unprotect_secret,
)


APP_NAME_EN = "UniversalWebCollector"
APP_NAME_CN = "通用网站采集中心"
APP_VERSION = "2026.06.09-ai-agent115"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
DEFAULT_TIMEOUT_SECONDS = 25
DEFAULT_SCROLL_TIMES = 3
DEFAULT_PAGE_LIMIT = 5
MAX_TEXT_LENGTH = 20000
MAX_LINKS = 300
MAX_IMAGES = 120
MAX_TABLE_ROWS = 200
AI_SNAPSHOT_TEXT_LIMIT = 12000


AI_PROVIDER_PRESETS = {
    "openai": {
        "name": "OpenAI",
        "api_format": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "models_url": "https://api.openai.com/v1/models",
        "models": [
            "gpt-5.2",
            "gpt-5.1",
            "gpt-5.1-mini",
            "gpt-5",
            "gpt-5-mini",
            "gpt-5-nano",
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4.1-nano",
            "gpt-4o",
            "gpt-4o-mini",
            "o4-mini",
            "o3",
        ],
        "default_model": "gpt-5.2",
    },
    "deepseek": {
        "name": "DeepSeek",
        "api_format": "openai_compatible",
        "base_url": "https://api.deepseek.com",
        "models_url": "https://api.deepseek.com/models",
        "models": [
            "deepseek-v4-flash",
            "deepseek-v4-pro",
            "deepseek-chat",
            "deepseek-reasoner",
            "deepseek-v3.2-exp",
            "deepseek-v3",
            "deepseek-r1",
        ],
        "default_model": "deepseek-v4-flash",
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "api_format": "anthropic",
        "base_url": "https://api.anthropic.com",
        "models_url": "https://api.anthropic.com/v1/models",
        "models": [
            "claude-opus-4-8",
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
            "claude-opus-4-5",
            "claude-sonnet-4-5-20250929",
            "claude-opus-4-1-20250805",
            "claude-sonnet-4-20250514",
            "claude-3-7-sonnet-20250219",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
            "claude-3-haiku-20240307",
        ],
        "default_model": "claude-sonnet-4-6",
    },
    "gemini": {
        "name": "Google Gemini",
        "api_format": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "models_url": "https://generativelanguage.googleapis.com/v1beta/models",
        "models": [
            "gemini-3.5-flash",
            "gemini-3.1-pro",
            "gemini-3.1-flash-live-preview",
            "gemini-3.1-flash-tts-preview",
            "gemini-3.1-flash-lite",
            "gemini-3-flash-preview",
            "gemini-3-pro-preview",
            "gemini-3-pro-image-preview",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
        ],
        "default_model": "gemini-2.5-flash",
    },
    "qwen": {
        "name": "阿里通义千问 DashScope",
        "api_format": "openai_compatible",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/models",
        "models": [
            "qwen3-max",
            "qwen3-plus",
            "qwen3-turbo",
            "qwen3-coder-plus",
            "qwen3-coder-flash",
            "qwen-max",
            "qwen-max-latest",
            "qwen-plus",
            "qwen-plus-latest",
            "qwen-flash",
            "qwen-turbo",
            "qwen-turbo-latest",
            "qwen-long",
            "qwen-vl-max",
            "qwen-vl-max-latest",
            "qwen-vl-plus",
            "qwen-omni-turbo",
            "qwen-audio-turbo",
            "qvq-max",
            "qwq-plus",
        ],
        "default_model": "qwen-plus",
    },
    "hunyuan": {
        "name": "腾讯混元 Hunyuan",
        "api_format": "openai_compatible",
        "base_url": "https://api.hunyuan.cloud.tencent.com/v1",
        "models_url": "",
        "models": [
            "hunyuan-turbos-latest",
            "hunyuan-turbo-latest",
            "hunyuan-large",
            "hunyuan-standard",
            "hunyuan-lite",
            "hunyuan-vision",
        ],
        "default_model": "hunyuan-turbos-latest",
    },
    "doubao": {
        "name": "火山方舟/豆包",
        "api_format": "openai_compatible",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "models_url": "",
        "models": [
            "doubao-seed-2-0-lite-260215",
            "doubao-seed-2-0-pro-260215",
            "doubao-seed-1-6-250615",
            "doubao-seed-1-6-thinking-250715",
            "doubao-1-5-pro-32k-250115",
            "doubao-1-5-lite-32k-250115",
            "doubao-1-5-vision-pro-32k-250115",
            "ark-code-latest",
        ],
        "default_model": "doubao-seed-2-0-lite-260215",
    },
    "kimi": {
        "name": "月之暗面 Kimi",
        "api_format": "openai_compatible",
        "base_url": "https://api.moonshot.ai/v1",
        "models_url": "https://api.moonshot.ai/v1/models",
        "models": [
            "kimi-latest",
            "kimi-k2-thinking-turbo",
            "moonshot-v1-128k",
            "moonshot-v1-32k",
            "moonshot-v1-8k",
            "moonshot-v1-auto",
            "moonshot-v1-vision-preview",
        ],
        "default_model": "moonshot-v1-128k",
    },
    "zhipu": {
        "name": "智谱 GLM",
        "api_format": "openai_compatible",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models_url": "https://open.bigmodel.cn/api/paas/v4/models",
        "models": [
            "glm-4.6",
            "glm-4.5",
            "glm-4.5-x",
            "glm-4.5-air",
            "glm-4.5-flash",
            "glm-4-plus",
            "glm-4-air",
            "glm-4-flash",
            "glm-z1-air",
            "glm-z1-flash",
        ],
        "default_model": "glm-4.5-flash",
    },
    "xai": {
        "name": "xAI Grok",
        "api_format": "openai_compatible",
        "base_url": "https://api.x.ai/v1",
        "models_url": "https://api.x.ai/v1/models",
        "models": [
            "grok-4",
            "grok-4-fast",
            "grok-3",
            "grok-3-mini",
            "grok-2-vision-latest",
            "grok-code-fast-1",
        ],
        "default_model": "grok-4-fast",
    },
    "mistral": {
        "name": "Mistral AI",
        "api_format": "openai_compatible",
        "base_url": "https://api.mistral.ai/v1",
        "models_url": "https://api.mistral.ai/v1/models",
        "models": [
            "mistral-large-latest",
            "mistral-medium-latest",
            "mistral-small-latest",
            "pixtral-large-latest",
            "ministral-8b-latest",
            "ministral-3b-latest",
            "codestral-latest",
        ],
        "default_model": "mistral-small-latest",
    },
    "groq": {
        "name": "GroqCloud",
        "api_format": "openai_compatible",
        "base_url": "https://api.groq.com/openai/v1",
        "models_url": "https://api.groq.com/openai/v1/models",
        "models": [
            "groq/compound",
            "groq/compound-mini",
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "qwen/qwen3-32b",
        ],
        "default_model": "openai/gpt-oss-120b",
    },
    "together": {
        "name": "Together AI",
        "api_format": "openai_compatible",
        "base_url": "https://api.together.xyz/v1",
        "models_url": "https://api.together.xyz/v1/models",
        "models": [
            "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
            "meta-llama/Llama-4-Scout-17B-16E-Instruct",
            "meta-llama/Llama-3.3-70B-Instruct-Turbo",
            "Qwen/Qwen3-235B-A22B-fp8-tput",
            "Qwen/Qwen3-32B",
            "deepseek-ai/DeepSeek-V3",
            "deepseek-ai/DeepSeek-R1",
        ],
        "default_model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    },
    "perplexity": {
        "name": "Perplexity Sonar",
        "api_format": "openai_compatible",
        "base_url": "https://api.perplexity.ai",
        "models_url": "",
        "models": [
            "sonar",
            "sonar-pro",
            "sonar-reasoning-pro",
            "sonar-deep-research",
        ],
        "default_model": "sonar-pro",
    },
    "openrouter": {
        "name": "OpenRouter",
        "api_format": "openai_compatible",
        "base_url": "https://openrouter.ai/api/v1",
        "models_url": "https://openrouter.ai/api/v1/models",
        "models": [
            "openrouter/auto",
            "openai/gpt-5.2",
            "openai/gpt-5.1",
            "openai/gpt-5-mini",
            "anthropic/claude-sonnet-4.6",
            "anthropic/claude-opus-4.8",
            "google/gemini-2.5-pro",
            "google/gemini-2.5-flash",
            "deepseek/deepseek-chat",
            "deepseek/deepseek-r1",
            "qwen/qwen3-max",
            "moonshotai/kimi-latest",
            "x-ai/grok-4-fast",
        ],
        "default_model": "openrouter/auto",
    },
    "siliconflow": {
        "name": "硅基流动 SiliconFlow",
        "api_format": "openai_compatible",
        "base_url": "https://api.siliconflow.cn/v1",
        "models_url": "https://api.siliconflow.cn/v1/models",
        "models": [
            "Qwen/Qwen3-235B-A22B",
            "Qwen/Qwen3-32B",
            "Qwen/Qwen2.5-VL-72B-Instruct",
            "deepseek-ai/DeepSeek-V3",
            "deepseek-ai/DeepSeek-R1",
            "zai-org/GLM-4.5",
            "moonshotai/Kimi-K2-Instruct",
            "BAAI/bge-m3",
            "Pro/Qwen/Qwen2.5-VL-7B-Instruct",
        ],
        "default_model": "Qwen/Qwen3-235B-A22B",
    },
    "thunderbit": {
        "name": "Thunderbit 抽取接口（第三方接口）",
        "api_format": "thunderbit_extract",
        "base_url": "https://openapi.thunderbit.com/openapi/v1",
        "models_url": "",
        "models": ["extract"],
        "default_model": "extract",
    },
    "custom": {
        "name": "自定义 OpenAI 兼容",
        "api_format": "openai_compatible",
        "base_url": "",
        "models_url": "",
        "models": ["custom-model"],
        "default_model": "custom-model",
    },
}


AI_MODEL_USE_CASE_PRESETS = {
    "web_scrape": {
        "name": "网页抓取推荐",
        "provider": "openai",
        "model": "gpt-5.2",
        "goal": "AI 建议列、自然语言采集任务、字段修复的均衡默认选择。",
    },
    "vision_file": {
        "name": "PDF/图片识别",
        "provider": "gemini",
        "model": "gemini-2.5-flash",
        "goal": "优先处理截图、图片和 PDF 转表格等视觉/多模态任务。",
    },
    "cheap_batch": {
        "name": "便宜批量",
        "provider": "qwen",
        "model": "qwen-flash",
        "goal": "适合大量页面的低成本批处理、简单字段补全和表格清洗。",
    },
    "strong_reasoning": {
        "name": "强推理修复字段",
        "provider": "deepseek",
        "model": "deepseek-reasoner",
        "goal": "适合复杂选择器修复、规则推理和失败原因分析。",
    },
}


def classify_error(error_text):
    text = compact_text(error_text or "", 3000)
    lower = text.lower()
    if not text:
        return {"category": "", "advice": ""}
    if any(token in lower for token in ("api key", "apikey", "unauthorized", "401", "403", "base url", "chat/completions", "generatecontent")):
        return {
            "category": "API 配置",
            "advice": "检查 API Key、Base URL、接口格式和模型名称，先在 AI 配置页点击测试 API。",
        }
    if any(token in lower for token in ("timeout", "timed out", "超时", "networkidle")):
        return {
            "category": "网络超时",
            "advice": "提高访问间隔，减少分页/子页面数量；动态网页可重试真实浏览器模式。",
        }
    if any(token in lower for token in ("name resolution", "dns", "getaddrinfo", "connection refused", "connection reset", "network", "urlopen error")):
        return {
            "category": "网络连接",
            "advice": "确认网址可打开、网络/代理正常；稍后重试或降低并发访问频率。",
        }
    if any(token in lower for token in ("captcha", "verify", "验证", "登录", "login", "access denied", "forbidden", "blocked", "反爬", "风控")):
        return {
            "category": "权限/反爬",
            "advice": "先用登录浏览器完成登录/验证，开启保留登录状态，并降低访问频率。",
        }
    if any(token in lower for token in ("selector", "locator", "css", "strict mode", "waiting for", "选择器")):
        return {
            "category": "选择器失效",
            "advice": "重新预采页面，用点选生成选择器或让 AI 修复问题列。",
        }
    if any(token in lower for token in ("pdf", "ocr", "image", "pypdf", "pillow")):
        return {
            "category": "文件解析",
            "advice": "确认文件可读；PDF/图片建议使用支持视觉/OCR 的远程模型重新解析。",
        }
    if any(token in lower for token in ("json", "parse", "decode", "响应格式", "no json")):
        return {
            "category": "解析失败",
            "advice": "检查页面/API 返回内容是否正常；可先预采一页再调整字段或模型。",
        }
    return {
        "category": "未知错误",
        "advice": "查看完整错误文本，先重试；若仍失败，降低采集规模并检查网页是否需要登录或特殊访问。",
    }


TEMPLATE_TYPES = {
    "auto": "自动识别",
    "ecommerce": "电商商品页",
    "article": "新闻文章页",
    "jobs": "招聘职位页",
    "company": "企业黄页页",
    "forum": "论坛帖子页",
    "gallery": "图片列表页",
    "real_estate": "房产房源页",
    "local_service": "本地服务页",
}


def app_base_dir():
    return os.path.dirname(os.path.abspath(__file__))


def default_data_dir():
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return os.path.join(local_app_data, APP_NAME_EN)
    return os.path.join(app_base_dir(), "universal_data")


DATA_DIR = os.path.abspath(
    os.environ.get("UNIVERSAL_COLLECTOR_DATA_DIR", default_data_dir())
)
DB_FILE = os.path.abspath(
    os.environ.get("UNIVERSAL_COLLECTOR_DB_FILE", os.path.join(DATA_DIR, "collector.sqlite3"))
)
TEMPLATE_FILE = os.path.abspath(
    os.environ.get("UNIVERSAL_COLLECTOR_TEMPLATE_FILE", os.path.join(DATA_DIR, "site_templates.json"))
)
AI_SETTINGS_FILE = os.path.abspath(
    os.environ.get("UNIVERSAL_COLLECTOR_AI_SETTINGS_FILE", os.path.join(DATA_DIR, "ai_settings.json"))
)
AI_CALL_LOG_FILE = os.path.abspath(
    os.environ.get("UNIVERSAL_COLLECTOR_AI_CALL_LOG_FILE", os.path.join(DATA_DIR, "ai_call_logs.jsonl"))
)
AI_REPAIR_HISTORY_FILE = os.path.abspath(
    os.environ.get("UNIVERSAL_COLLECTOR_AI_REPAIR_HISTORY_FILE", os.path.join(DATA_DIR, "ai_repair_history.jsonl"))
)
SCHEDULE_FILE = os.path.abspath(
    os.environ.get("UNIVERSAL_COLLECTOR_SCHEDULE_FILE", os.path.join(DATA_DIR, "schedules.json"))
)
CHANGE_ALERT_STATE_FILE = os.path.abspath(
    os.environ.get("UNIVERSAL_COLLECTOR_CHANGE_ALERT_STATE_FILE", os.path.join(DATA_DIR, "change_alert_states.json"))
)
RISK_CONFIRMATION_FILE = os.path.abspath(
    os.environ.get("UNIVERSAL_COLLECTOR_RISK_CONFIRMATION_FILE", os.path.join(DATA_DIR, "risk_confirmations.json"))
)
BROWSER_PROFILE_DIR = os.path.abspath(
    os.environ.get(
        "UNIVERSAL_COLLECTOR_BROWSER_PROFILE_DIR",
        os.path.join(DATA_DIR, "browser-profile"),
    )
)
STARTUP_LOG_FILE = os.path.abspath(
    os.environ.get(
        "UNIVERSAL_COLLECTOR_STARTUP_LOG_FILE",
        os.path.join(DATA_DIR, "startup_error.log"),
    )
)
SELF_TEST_ERROR_LOG_FILE = os.path.abspath(
    os.environ.get(
        "UNIVERSAL_COLLECTOR_SELF_TEST_ERROR_LOG_FILE",
        os.path.join(DATA_DIR, "self_test_error.log"),
    )
)


def runtime_path(env_name, fallback):
    return os.path.abspath(os.environ.get(env_name, fallback))


def runtime_data_dir():
    return runtime_path("UNIVERSAL_COLLECTOR_DATA_DIR", DATA_DIR)


def runtime_db_file():
    return runtime_path("UNIVERSAL_COLLECTOR_DB_FILE", os.path.join(runtime_data_dir(), "collector.sqlite3"))


def runtime_template_file():
    return runtime_path("UNIVERSAL_COLLECTOR_TEMPLATE_FILE", os.path.join(runtime_data_dir(), "site_templates.json"))


def runtime_ai_settings_file():
    return runtime_path("UNIVERSAL_COLLECTOR_AI_SETTINGS_FILE", os.path.join(runtime_data_dir(), "ai_settings.json"))


def runtime_ai_call_log_file():
    return runtime_path("UNIVERSAL_COLLECTOR_AI_CALL_LOG_FILE", os.path.join(runtime_data_dir(), "ai_call_logs.jsonl"))


def runtime_ai_repair_history_file():
    return runtime_path("UNIVERSAL_COLLECTOR_AI_REPAIR_HISTORY_FILE", os.path.join(runtime_data_dir(), "ai_repair_history.jsonl"))


def runtime_schedule_file():
    return runtime_path("UNIVERSAL_COLLECTOR_SCHEDULE_FILE", os.path.join(runtime_data_dir(), "schedules.json"))


def runtime_change_alert_state_file():
    return runtime_path("UNIVERSAL_COLLECTOR_CHANGE_ALERT_STATE_FILE", os.path.join(runtime_data_dir(), "change_alert_states.json"))


def runtime_risk_confirmation_file():
    return runtime_path("UNIVERSAL_COLLECTOR_RISK_CONFIRMATION_FILE", os.path.join(runtime_data_dir(), "risk_confirmations.json"))


def runtime_startup_log_file():
    return runtime_path("UNIVERSAL_COLLECTOR_STARTUP_LOG_FILE", os.path.join(runtime_data_dir(), "startup_error.log"))


def runtime_self_test_error_log_file():
    return runtime_path("UNIVERSAL_COLLECTOR_SELF_TEST_ERROR_LOG_FILE", os.path.join(runtime_data_dir(), "self_test_error.log"))


def runtime_change_alert_log_file():
    return os.path.join(runtime_data_dir(), "change_alerts.json")


def ensure_runtime_dirs():
    os.makedirs(runtime_data_dir(), exist_ok=True)
    os.makedirs(os.path.dirname(runtime_db_file()), exist_ok=True)
    os.makedirs(os.path.dirname(runtime_template_file()), exist_ok=True)
    os.makedirs(os.path.dirname(runtime_ai_settings_file()), exist_ok=True)
    os.makedirs(os.path.dirname(runtime_ai_call_log_file()), exist_ok=True)
    os.makedirs(os.path.dirname(runtime_ai_repair_history_file()), exist_ok=True)
    os.makedirs(os.path.dirname(runtime_schedule_file()), exist_ok=True)
    os.makedirs(os.path.dirname(runtime_change_alert_state_file()), exist_ok=True)
    os.makedirs(os.path.dirname(runtime_risk_confirmation_file()), exist_ok=True)
    os.makedirs(os.path.dirname(BROWSER_PROFILE_DIR), exist_ok=True)
    os.makedirs(os.path.dirname(runtime_startup_log_file()), exist_ok=True)
    os.makedirs(os.path.dirname(runtime_self_test_error_log_file()), exist_ok=True)


class CollectorDatabase(_CoreCollectorDatabase):
    def __init__(self, db_file=None):
        super().__init__(
            db_file=db_file,
            db_file_provider=runtime_db_file,
            ensure_runtime_dirs_func=ensure_runtime_dirs,
        )


def append_ai_call_log(entry, file_path=None):
    file_path = file_path or runtime_ai_call_log_file()
    ensure_runtime_dirs()
    return append_jsonl_entry(file_path, entry)


def load_ai_call_logs(limit=200, file_path=None):
    file_path = file_path or runtime_ai_call_log_file()
    ensure_runtime_dirs()
    return load_jsonl_entries(file_path, limit)


def append_ai_repair_history(entry, file_path=None):
    file_path = file_path or runtime_ai_repair_history_file()
    ensure_runtime_dirs()
    return append_jsonl_entry(file_path, entry)


def load_ai_repair_history(limit=100, file_path=None):
    file_path = file_path or runtime_ai_repair_history_file()
    ensure_runtime_dirs()
    return load_jsonl_entries(file_path, limit)


def summarize_ai_call_logs(logs=None):
    source_logs = load_ai_call_logs(0) if logs is None else list(logs or [])
    return summarize_ai_call_log_rows(source_logs)


def clear_ai_call_logs(file_path=None):
    file_path = file_path or runtime_ai_call_log_file()
    ensure_runtime_dirs()
    return clear_jsonl_file(file_path)


def _is_under_runtime_data_dir(path):
    try:
        root = os.path.normcase(os.path.abspath(runtime_data_dir()))
        target = os.path.normcase(os.path.abspath(path))
        return os.path.commonpath([root, target]) == root
    except Exception:
        return False


def remove_runtime_path(path):
    path = os.path.abspath(path)
    if not _is_under_runtime_data_dir(path):
        return False, f"{path}：路径不在运行数据目录内，已跳过"
    if not os.path.exists(path):
        return False, ""
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        return True, ""
    except Exception as exc:
        return False, f"{path}：{exc}"


def cleanup_user_data(options=None):
    options = options or {}
    targets = []
    if options.get("api_settings"):
        targets.append(("AI 配置/API Key", runtime_ai_settings_file()))
    if options.get("history"):
        targets.extend(
            [
                ("历史数据库", runtime_db_file()),
                ("任务计划", runtime_schedule_file()),
                ("变更提醒状态", runtime_change_alert_state_file()),
                ("变更提醒记录", runtime_change_alert_log_file()),
                ("风险确认记录", runtime_risk_confirmation_file()),
            ]
        )
    if options.get("ai_logs"):
        targets.extend(
            [
                ("AI 调用日志", runtime_ai_call_log_file()),
                ("AI 修复历史", runtime_ai_repair_history_file()),
            ]
        )
    if options.get("browser_profile"):
        targets.append(("浏览器登录态", BROWSER_PROFILE_DIR))
    if options.get("templates"):
        targets.append(("模板库", runtime_template_file()))

    removed = []
    failed = []
    for label, path in targets:
        ok, message = remove_runtime_path(path)
        if ok:
            removed.append({"item": label, "path": path})
        elif message:
            failed.append(message)
    ensure_runtime_dirs()
    return {"removed": removed, "failed": failed}


def now_text():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def clean_text(value, limit=MAX_TEXT_LENGTH):
    if value is None:
        return ""
    text = unescape(str(value))
    text = re.sub(r"[\r\t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ ]{2,}", " ", text)
    text = text.strip()
    if len(text) > limit:
        return text[:limit].rstrip() + "..."
    return text


def compact_text(value, limit=500):
    return re.sub(r"\s+", " ", clean_text(value, limit)).strip()


def normalize_schedule_item(item):
    source = dict(item or {})
    schedule_id = clean_text(source.get("id") or "", 80)
    if not schedule_id:
        schedule_id = f"schedule-{int(time.time() * 1000)}"
    interval_minutes = int(source.get("interval_minutes") or 30)
    interval_minutes = max(1, min(1440, interval_minutes))
    last_run_at = clean_text(source.get("last_run_at") or "", 40)
    next_run_at = clean_text(source.get("next_run_at") or "", 40)
    return {
        "id": schedule_id,
        "name": clean_text(source.get("name") or "未命名计划", 120),
        "enabled": bool(source.get("enabled", True)),
        "interval_minutes": interval_minutes,
        "created_at": clean_text(source.get("created_at") or now_text(), 40),
        "updated_at": clean_text(source.get("updated_at") or now_text(), 40),
        "last_run_at": last_run_at,
        "next_run_at": next_run_at,
        "run_count": int(source.get("run_count") or 0),
        "last_status": clean_text(source.get("last_status") or "待运行", 80),
        "last_message": clean_text(source.get("last_message") or "", 1000),
        "config": source.get("config") if isinstance(source.get("config"), dict) else {},
    }


def load_schedules(file_path=None):
    file_path = file_path or runtime_schedule_file()
    ensure_runtime_dirs()
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return []
    if isinstance(payload, dict):
        items = payload.get("schedules", [])
    else:
        items = payload
    return [normalize_schedule_item(item) for item in items if isinstance(item, dict)]


def save_schedules(schedules, file_path=None):
    file_path = file_path or runtime_schedule_file()
    ensure_runtime_dirs()
    rows = [normalize_schedule_item(item) for item in schedules or [] if isinstance(item, dict)]
    temp_path = f"{file_path}.tmp.{os.getpid()}"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump({"schedules": rows}, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, file_path)
    return rows


def load_change_alert_states(file_path=None):
    file_path = file_path or runtime_change_alert_state_file()
    ensure_runtime_dirs()
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return {}
    states = payload.get("states", payload) if isinstance(payload, dict) else {}
    if not isinstance(states, dict):
        return {}
    result = {}
    for key, raw in states.items():
        if not isinstance(raw, dict):
            continue
        status = str(raw.get("status", "未读")).strip() or "未读"
        if status not in ("未读", "已处理", "忽略"):
            status = "未读"
        result[str(key)] = {
            "status": status,
            "updated_at": str(raw.get("updated_at", "")),
            "note": str(raw.get("note", "")),
        }
    return result


def save_change_alert_states(states, file_path=None):
    file_path = file_path or runtime_change_alert_state_file()
    ensure_runtime_dirs()
    clean_states = {}
    for key, raw in (states or {}).items():
        if not isinstance(raw, dict):
            continue
        status = str(raw.get("status", "未读")).strip() or "未读"
        if status not in ("未读", "已处理", "忽略"):
            status = "未读"
        clean_states[str(key)] = {
            "status": status,
            "updated_at": str(raw.get("updated_at", "")),
            "note": str(raw.get("note", "")),
        }
    temp_path = f"{file_path}.tmp.{os.getpid()}"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump({"states": clean_states}, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, file_path)
    return clean_states


def change_alert_key(alert):
    payload = {
        "time": alert.get("监控时间", ""),
        "url": alert.get("网址", ""),
        "field": alert.get("字段", ""),
        "old": alert.get("旧值", ""),
        "new": alert.get("新值", ""),
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:24]


def load_risk_confirmations(file_path=None):
    file_path = file_path or runtime_risk_confirmation_file()
    ensure_runtime_dirs()
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return {}
    states = payload.get("states", payload) if isinstance(payload, dict) else {}
    if not isinstance(states, dict):
        return {}
    result = {}
    for key, raw in states.items():
        if not isinstance(raw, dict):
            continue
        result[str(key)] = {
            "confirmed_at": str(raw.get("confirmed_at", "")),
            "expires_at": str(raw.get("expires_at", "")),
            "note": str(raw.get("note", "")),
        }
    return result


def save_risk_confirmations(states, file_path=None):
    file_path = file_path or runtime_risk_confirmation_file()
    ensure_runtime_dirs()
    clean_states = {}
    for key, raw in (states or {}).items():
        if not isinstance(raw, dict):
            continue
        clean_states[str(key)] = {
            "confirmed_at": str(raw.get("confirmed_at", "")),
            "expires_at": str(raw.get("expires_at", "")),
            "note": str(raw.get("note", "")),
        }
    temp_path = f"{file_path}.tmp.{os.getpid()}"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump({"states": clean_states}, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, file_path)
    return clean_states


def risk_confirmation_key(urls, risk_item):
    risk_item = risk_item or {}
    domains = sorted({url_domain(url) for url in urls or [] if url_domain(url)})
    domain_text = ",".join(domains[:12]) or "unknown"
    payload = {
        "domains": domain_text,
        "check": risk_item.get("检查项", ""),
        "detail": risk_item.get("说明", ""),
        "advice": risk_item.get("建议", ""),
        "ref": risk_item.get("参考", ""),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"{domain_text}|{risk_item.get('检查项', '')}|{digest}"


def schedule_next_run_text(interval_minutes, from_time=None):
    base_time = from_time if isinstance(from_time, (int, float)) else time.time()
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(base_time + int(interval_minutes or 1) * 60))


def new_schedule_item(name, interval_minutes, config):
    interval_minutes = max(1, min(1440, int(interval_minutes or 30)))
    created_at = now_text()
    return normalize_schedule_item(
        {
            "id": f"schedule-{int(time.time() * 1000)}",
            "name": name or "未命名计划",
            "enabled": True,
            "interval_minutes": interval_minutes,
            "created_at": created_at,
            "updated_at": created_at,
            "next_run_at": schedule_next_run_text(interval_minutes),
            "config": dict(config or {}),
        }
    )


def normalize_url(url, base_url=""):
    url = clean_text(url, 2000)
    if not url:
        return ""
    if base_url:
        url = urljoin(base_url, url)
    parsed = urlparse(url)
    if not parsed.scheme and not base_url:
        if url.startswith("//"):
            url = "https:" + url
        elif "." in url and not url.lower().startswith(("javascript:", "mailto:", "tel:")):
            url = "https://" + url
    return url


def url_domain(url):
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def site_root_url(url):
    parsed = urlparse(normalize_url(url))
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def robots_txt_url(url):
    root = site_root_url(url)
    return f"{root}/robots.txt" if root else ""


def assess_scrape_risks(
    urls,
    use_browser=True,
    keep_login_state=False,
    delay_seconds=1,
    page_limit=1,
    scrape_subpages=False,
    subpage_limit=0,
    field_rules=None,
):
    normalized_urls = [normalize_url(item) for item in urls or [] if normalize_url(item)]
    field_rules = field_rules or []
    risks = []

    def add(level, item, detail, advice, ref_url=""):
        risks.append(
            {
                "级别": level,
                "检查项": item,
                "说明": detail,
                "建议": advice,
                "参考": ref_url,
            }
        )

    if not normalized_urls:
        add("需处理", "网址", "未填写采集网址。", "先填写至少一个 http/https 网址。")
        return risks

    domains = sorted({url_domain(url) for url in normalized_urls if url_domain(url)})
    for domain in domains[:8]:
        first_url = next((url for url in normalized_urls if url_domain(url) == domain), "")
        add(
            "需确认",
            "robots.txt",
            f"{domain} 可能有 robots.txt 或站点条款限制。",
            "采集前打开参考链接确认允许范围；不采集登录后私密、付费或禁止抓取内容。",
            robots_txt_url(first_url),
        )

    total_scope = len(normalized_urls) * max(1, int(page_limit or 1))
    if scrape_subpages:
        total_scope += len(normalized_urls) * max(0, int(subpage_limit or 0))
    if total_scope > 200:
        add("高", "采集规模", f"预计访问页面数可能超过 {total_scope}。", "先小批量预采，确认字段和频率后再扩大。")
    elif total_scope > 50:
        add("需确认", "采集规模", f"预计访问页面数约 {total_scope}。", "建议先降低页数/子页面上限，避免给网站造成压力。")

    if float(delay_seconds or 0) < 1 and total_scope > 5:
        add("高", "访问频率", "访问间隔低于 1 秒且页面数较多。", "把访问间隔调到 1-3 秒以上，必要时分批运行。")
    elif float(delay_seconds or 0) < 1:
        add("需确认", "访问频率", "访问间隔低于 1 秒。", "若不是自己的站点，建议增加访问间隔。")

    if keep_login_state:
        add(
            "高",
            "登录态",
            "当前启用了保留登录状态，可能访问账号专属或非公开内容。",
            "只采集自己有权处理的数据，不导出私密页面、订单、账号资料或受限内容。",
        )

    sensitive_words = (
        "邮箱",
        "email",
        "电话",
        "手机",
        "phone",
        "tel",
        "身份证",
        "证件",
        "地址",
        "联系人",
        "contact",
    )
    sensitive_fields = []
    for rule in field_rules:
        name = rule.name if isinstance(rule, FieldRule) else str(getattr(rule, "name", "") or "")
        selector = rule.selector if isinstance(rule, FieldRule) else str(getattr(rule, "selector", "") or "")
        text = f"{name} {selector}".lower()
        if any(word.lower() in text for word in sensitive_words):
            sensitive_fields.append(name or selector)
    if sensitive_fields:
        add(
            "高",
            "敏感字段",
            f"字段可能包含个人联系方式或敏感信息：{', '.join(sensitive_fields[:6])}",
            "导出前确认合法来源、用途、最小化字段，并避免批量传播个人信息。",
        )

    if use_browser and total_scope > 30:
        add("需确认", "动态浏览器", "真实浏览器会加载脚本、图片和更多资源。", "大批量任务建议先预采一页，确认必要后再运行。")

    if not any(row.get("级别") in ("高", "需处理") for row in risks):
        add("正常", "基础检查", "未发现明显高风险配置。", "仍建议遵守站点条款、robots.txt 和合理访问频率。")
    return risks


def list_to_text(value, limit=32000):
    if isinstance(value, str):
        return clean_text(value, limit)
    if value is None:
        return ""
    return clean_text(json.dumps(value, ensure_ascii=False), limit)


def default_provider_ai_settings(provider):
    preset = ai_preset_for(provider)
    return {
        "provider": provider,
        "provider_name": preset["name"],
        "api_format": preset["api_format"],
        "base_url": preset["base_url"],
        "models_url": preset["models_url"],
        "model": preset["default_model"],
        "models": list(preset.get("models", [])),
        "model_cache": list(preset.get("models", [])),
        "models_updated_at": "",
        "models_refresh_error": "",
        "connection_status": "未测试",
        "connection_tested_at": "",
        "connection_error": "",
        "api_key": "",
        "api_keys": [],
        "active_api_key_name": "",
        "auto_apply_use_case": True,
        "temperature": 0.1,
        "timeout_seconds": 60,
    }


def unique_model_names(models):
    result = []
    seen = set()
    for model in models or []:
        model = str(model).strip()
        if not model or model in seen:
            continue
        seen.add(model)
        result.append(model)
    return result


def model_tags(model_name, provider=""):
    model = str(model_name or "").strip()
    lower = model.lower()
    tags = []
    preset = AI_PROVIDER_PRESETS.get(provider, {})
    if model and model == preset.get("default_model"):
        tags.append("推荐")
    if any(token in lower for token in ("vision", "vl", "omni", "pixtral", "image", "gpt-4o", "gemini", "qwen-vl")):
        tags.append("视觉")
    if any(token in lower for token in ("mini", "nano", "lite", "flash", "turbo", "small", "haiku", "instant", "8b", "3b")):
        tags.append("低价")
    if any(token in lower for token in ("flash", "turbo", "fast", "instant", "lite")):
        tags.append("高速")
    if any(token in lower for token in ("reason", "thinking", "r1", "o3", "o4", "qwq", "qvq", "z1")):
        tags.append("推理")
    if any(token in lower for token in ("coder", "code", "codestral")):
        tags.append("代码")
    if any(token in lower for token in ("128k", "long", "1m", "200k", "1-million")):
        tags.append("长文本")
    if "pro" in lower or "opus" in lower or "large" in lower or "max" in lower:
        tags.append("强力")
    return unique_model_names(tags)


def ai_provider_preset_health():
    checks = []
    for key, preset in AI_PROVIDER_PRESETS.items():
        models = unique_model_names(preset.get("models", []))
        default_model = (preset.get("default_model") or "").strip()
        api_format = preset.get("api_format", "openai_compatible")
        models_url = (preset.get("models_url") or "").strip()
        minimum = 1 if api_format == "thunderbit_extract" else 3
        status = "正常"
        issues = []
        if len(models) < minimum:
            status = "需补充"
            issues.append(f"内置模型少于 {minimum} 个")
        if default_model and default_model not in models:
            status = "错误"
            issues.append("默认模型不在内置模型列表中")
        if api_format in {"openai_compatible", "anthropic", "gemini"} and preset.get("base_url") and not models_url:
            issues.append("未提供在线模型列表 URL，需要用户手动填模型")
        checks.append(
            {
                "provider": key,
                "provider_name": preset.get("name", key),
                "api_format": api_format,
                "model_count": len(models),
                "default_model": default_model,
                "models_url": models_url,
                "status": status,
                "issues": issues,
            }
        )
    return checks


def ai_provider_runtime_overview(settings=None):
    settings = settings or default_ai_settings()
    providers = settings.get("providers") if isinstance(settings, dict) else {}
    if not isinstance(providers, dict):
        providers = {}
    preset_checks = {
        item.get("provider"): item
        for item in ai_provider_preset_health()
    }
    rows = []
    active_provider = settings.get("provider") if isinstance(settings, dict) else ""
    for provider, preset in AI_PROVIDER_PRESETS.items():
        provider_settings = merge_provider_preset(
            provider,
            providers.get(provider, default_provider_ai_settings(provider)),
        )
        models = unique_model_names(
            (provider_settings.get("model_cache") or [])
            + (provider_settings.get("models") or [])
            + preset.get("models", [])
        )
        api_keys = normalize_api_key_entries(
            provider_settings.get("api_keys"),
            provider_settings.get("api_key", ""),
            provider_settings.get("active_api_key_name", ""),
        )
        active_name = provider_settings.get("active_api_key_name") or (api_keys[0]["name"] if api_keys else "")
        active_key = next((item for item in api_keys if item.get("name") == active_name), api_keys[0] if api_keys else {})
        key_statuses = [item.get("status") or "未测试" for item in api_keys]
        if any(status == "可用" for status in key_statuses):
            key_status = "有可用 Key"
        elif any(status == "失败" for status in key_statuses):
            key_status = "Key 有失败"
        elif api_keys:
            key_status = "Key 未测试"
        else:
            key_status = "未保存 Key"
        diagnosis = diagnose_ai_settings(provider_settings)
        if diagnosis.get("ok"):
            if any(row.get("level") == "需确认" for row in diagnosis.get("checks", [])):
                config_status = "需确认"
            else:
                config_status = "正常"
        else:
            config_status = "错误"
        preset_health = preset_checks.get(provider, {})
        rows.append(
            {
                "provider": provider,
                "provider_name": preset.get("name", provider),
                "active": provider == active_provider,
                "api_format": provider_settings.get("api_format", preset.get("api_format", "")),
                "base_url": provider_settings.get("base_url", ""),
                "model": provider_settings.get("model", ""),
                "model_count": len(models),
                "models_url": provider_settings.get("models_url", ""),
                "models_updated_at": provider_settings.get("models_updated_at", ""),
                "models_refresh_error": provider_settings.get("models_refresh_error", ""),
                "connection_status": provider_settings.get("connection_status", "未测试"),
                "connection_tested_at": provider_settings.get("connection_tested_at", ""),
                "connection_error": provider_settings.get("connection_error", ""),
                "key_count": len(api_keys),
                "active_key_name": active_name,
                "active_key_mask": mask_api_key(active_key.get("key", "")) if active_key else "未填写",
                "key_status": key_status,
                "config_status": config_status,
                "preset_status": preset_health.get("status", ""),
                "issues": "; ".join(preset_health.get("issues") or []),
            }
        )
    rows.sort(key=lambda item: (not item.get("active"), item.get("provider_name", "")))
    return rows


def refresh_ai_provider_models(settings=None, providers=None, now_text=None):
    settings = deepcopy(settings or load_ai_settings())
    provider_settings_map = settings.get("providers") if isinstance(settings, dict) else {}
    if not isinstance(provider_settings_map, dict):
        provider_settings_map = {}
    selected = list(providers or AI_PROVIDER_PRESETS.keys())
    timestamp = now_text or time.strftime("%Y-%m-%d %H:%M:%S")
    results = []
    for provider in selected:
        preset = ai_preset_for(provider)
        provider_settings = merge_provider_preset(
            provider,
            provider_settings_map.get(provider, default_provider_ai_settings(provider)),
        )
        api_format = provider_settings.get("api_format", preset.get("api_format", "openai_compatible"))
        models_url = (provider_settings.get("models_url") or "").strip()
        status = "失败"
        fetched_models = []
        message = ""
        if api_format == "thunderbit_extract":
            status = "跳过"
            message = "第三方抽取接口不需要拉取模型。"
        elif not provider_settings.get("api_key") and not str(provider_settings.get("base_url", "")).startswith(("http://127.0.0.1", "http://localhost")):
            status = "跳过"
            message = "未保存 API Key，无法访问在线模型列表。"
        elif api_format != "gemini" and not models_url:
            status = "跳过"
            message = "该厂商未提供统一模型列表 URL，请手动填写模型名。"
        else:
            try:
                fetched_models = unique_model_names(AIClient(provider_settings).fetch_models())
                if fetched_models:
                    cached_models = unique_model_names(
                        fetched_models
                        + (provider_settings.get("model_cache") or [])
                        + (provider_settings.get("models") or [])
                    )
                    provider_settings["models"] = unique_model_names((provider_settings.get("models") or []) + fetched_models)
                    provider_settings["model_cache"] = cached_models
                    if not provider_settings.get("model") or provider_settings.get("model") not in cached_models:
                        provider_settings["model"] = fetched_models[0]
                    provider_settings["models_updated_at"] = timestamp
                    provider_settings["models_refresh_error"] = ""
                    status = "成功"
                    message = f"拉取 {len(fetched_models)} 个模型。"
                else:
                    status = "失败"
                    message = "在线接口返回了空模型列表。"
                    provider_settings["models_refresh_error"] = message
            except Exception as exc:
                status = "失败"
                message = str(exc)[:500]
                provider_settings["models_refresh_error"] = message
        provider_settings_map[provider] = provider_settings
        results.append(
            {
                "provider": provider,
                "provider_name": preset.get("name", provider),
                "status": status,
                "model_count": len(fetched_models),
                "message": message,
                "models_updated_at": provider_settings.get("models_updated_at", ""),
            }
        )
    settings["providers"] = provider_settings_map
    active_provider = settings.get("provider") or "openai"
    if active_provider in provider_settings_map:
        settings.update(provider_settings_map[active_provider])
    return {"updated_at": timestamp, "results": results, "settings": settings}


def update_provider_active_key_state(provider_settings, status, error_text="", tested_at=""):
    provider_settings = dict(provider_settings or {})
    api_keys = normalize_api_key_entries(
        provider_settings.get("api_keys"),
        provider_settings.get("api_key", ""),
        provider_settings.get("active_api_key_name", ""),
    )
    active_name = provider_settings.get("active_api_key_name") or (api_keys[0]["name"] if api_keys else "")
    active_key = provider_settings.get("api_key", "")
    changed = False
    for entry in api_keys:
        if (active_name and entry.get("name") == active_name) or (active_key and entry.get("key") == active_key):
            entry["status"] = status
            entry["last_tested_at"] = tested_at or time.strftime("%Y-%m-%d %H:%M:%S")
            entry["last_error"] = str(error_text or "")[:500]
            active_name = entry.get("name", active_name)
            active_key = entry.get("key", active_key)
            changed = True
            break
    if active_key and not changed:
        api_keys.append(
            {
                "name": active_name or "默认 Key",
                "key": active_key,
                "status": status,
                "last_tested_at": tested_at or time.strftime("%Y-%m-%d %H:%M:%S"),
                "last_error": str(error_text or "")[:500],
            }
        )
    provider_settings["api_keys"] = api_keys
    provider_settings["active_api_key_name"] = active_name
    provider_settings["api_key"] = active_key
    return provider_settings


def test_ai_provider_connectivity(settings=None, providers=None, now_text=None):
    settings = deepcopy(settings or load_ai_settings())
    provider_settings_map = settings.get("providers") if isinstance(settings, dict) else {}
    if not isinstance(provider_settings_map, dict):
        provider_settings_map = {}
    selected = list(providers or AI_PROVIDER_PRESETS.keys())
    timestamp = now_text or time.strftime("%Y-%m-%d %H:%M:%S")
    results = []
    for provider in selected:
        preset = ai_preset_for(provider)
        provider_settings = merge_provider_preset(
            provider,
            provider_settings_map.get(provider, default_provider_ai_settings(provider)),
        )
        api_format = provider_settings.get("api_format", preset.get("api_format", "openai_compatible"))
        status = "失败"
        message = ""
        if api_format == "thunderbit_extract":
            status = "跳过"
            message = "第三方抽取接口不是通用聊天模型，请用网页抽取任务验证。"
        elif not provider_settings.get("api_key") and not str(provider_settings.get("base_url", "")).startswith(("http://127.0.0.1", "http://localhost")):
            status = "跳过"
            message = "未保存 API Key，无法测试模型调用。"
        elif not provider_settings.get("model"):
            status = "跳过"
            message = "未选择模型，无法测试调用。"
        else:
            try:
                result = AIClient(provider_settings).test_connection()
                if isinstance(result, dict) and result.get("ok") is False:
                    raise RuntimeError(result.get("message") or "连接测试返回失败。")
                status = "成功"
                message = result.get("message", "连接成功。") if isinstance(result, dict) else "连接成功。"
            except Exception as exc:
                status = "失败"
                message = str(exc)[:500]
        provider_settings["connection_status"] = status
        provider_settings["connection_tested_at"] = timestamp
        provider_settings["connection_error"] = "" if status == "成功" else message
        if status in {"成功", "失败"}:
            provider_settings = update_provider_active_key_state(
                provider_settings,
                "可用" if status == "成功" else "失败",
                "" if status == "成功" else message,
                timestamp,
            )
        provider_settings_map[provider] = provider_settings
        results.append(
            {
                "provider": provider,
                "provider_name": preset.get("name", provider),
                "status": status,
                "model": provider_settings.get("model", ""),
                "message": message,
                "tested_at": timestamp,
            }
        )
    settings["providers"] = provider_settings_map
    active_provider = settings.get("provider") or "openai"
    if active_provider in provider_settings_map:
        settings.update(provider_settings_map[active_provider])
    return {"tested_at": timestamp, "results": results, "settings": settings}


def merge_provider_preset(provider, provider_settings):
    preset = ai_preset_for(provider)
    merged = default_provider_ai_settings(provider)
    if isinstance(provider_settings, dict):
        merged.update(provider_settings)
    merged["provider"] = provider
    if provider in AI_PROVIDER_PRESETS:
        merged["provider_name"] = preset["name"]
        for key in ("api_format", "base_url", "models_url"):
            if not merged.get(key):
                merged[key] = preset.get(key, "")
    preset_models = list(preset.get("models", []))
    saved_models = list(merged.get("models") or [])
    saved_cache = list(merged.get("model_cache") or [])
    merged["models"] = unique_model_names(preset_models + saved_models)
    merged["model_cache"] = unique_model_names(saved_cache + merged["models"])
    if not merged.get("model"):
        merged["model"] = preset.get("default_model") or (merged["model_cache"][0] if merged["model_cache"] else "")
    api_keys = normalize_api_key_entries(merged.get("api_keys"), merged.get("api_key", ""), merged.get("active_api_key_name", ""))
    merged["api_keys"] = api_keys
    active_name = merged.get("active_api_key_name") or (api_keys[0]["name"] if api_keys else "")
    if api_keys and active_name not in {item["name"] for item in api_keys}:
        active_name = api_keys[0]["name"]
    merged["active_api_key_name"] = active_name
    if api_keys:
        active_entry = next((item for item in api_keys if item["name"] == active_name), api_keys[0])
        merged["api_key"] = active_entry.get("key", "")
    return merged


def mask_api_key(api_key):
    api_key = str(api_key or "").strip()
    if not api_key:
        return "未填写"
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}...{api_key[-4:]}"


def normalize_api_key_entries(api_keys=None, legacy_key="", active_name=""):
    result = []
    seen = set()
    for raw in api_keys or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        key = str(raw.get("key") or "").strip()
        if not key:
            continue
        if not name:
            name = f"Key {len(result) + 1}"
        base_name = name
        index = 2
        while name in seen:
            name = f"{base_name} {index}"
            index += 1
        seen.add(name)
        entry = {"name": name, "key": key}
        for meta_key in ("status", "last_tested_at", "last_error"):
            if raw.get(meta_key):
                entry[meta_key] = str(raw.get(meta_key))
        result.append(entry)
    legacy_key = str(legacy_key or "").strip()
    if legacy_key and not any(item["key"] == legacy_key for item in result):
        name = str(active_name or "默认 Key").strip() or "默认 Key"
        base_name = name
        index = 2
        while name in seen:
            name = f"{base_name} {index}"
            index += 1
        result.insert(0, {"name": name, "key": legacy_key})
    return result


def diagnose_ai_settings(settings):
    settings = settings or {}
    provider = settings.get("provider") or "custom"
    preset = ai_preset_for(provider)
    provider_name = settings.get("provider_name") or preset.get("name") or provider
    api_format = (settings.get("api_format") or "openai_compatible").strip()
    base_url = (settings.get("base_url") or "").strip()
    models_url = (settings.get("models_url") or "").strip()
    model = (settings.get("model") or "").strip()
    api_key = (settings.get("api_key") or "").strip()
    known_models = unique_model_names((settings.get("model_cache") or []) + (settings.get("models") or []) + preset.get("models", []))
    rows = []

    def add(level, item, status, advice):
        rows.append({"level": level, "item": item, "status": status, "advice": advice})

    if provider in AI_PROVIDER_PRESETS:
        add("正常", "服务商", provider_name, "已使用内置服务商预设；可按需覆盖 Base URL、模型列表 URL 和模型。")
    else:
        add("需确认", "服务商", provider_name, "未知服务商会按自定义 OpenAI 兼容接口处理，请确认接口格式。")

    expected_format = preset.get("api_format")
    if provider in AI_PROVIDER_PRESETS and expected_format and api_format != expected_format:
        add("错误", "接口格式", f"当前 {api_format}，预设应为 {expected_format}", "切回该服务商默认接口格式，或改用自定义服务商。")
    else:
        add("正常", "接口格式", api_format, "接口格式与当前服务商匹配。")

    if not base_url:
        add("错误", "Base URL", "未填写", "填写服务商 API Base URL，OpenAI 兼容接口通常以 /v1 结尾。")
    else:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            add("错误", "Base URL", base_url, "Base URL 必须是完整 http/https 地址。")
        elif api_format == "openai_compatible" and not base_url.rstrip("/").endswith("/v1") and provider not in {"deepseek", "perplexity"}:
            add("需确认", "Base URL", base_url, "OpenAI 兼容服务通常以 /v1 结尾；若测试失败，先修正这个地址。")
        elif provider in AI_PROVIDER_PRESETS and preset.get("base_url") and base_url.rstrip("/") != preset.get("base_url", "").rstrip("/"):
            add("需确认", "Base URL", base_url, f"与内置预设不同；默认地址是 {preset.get('base_url')}。")
        else:
            add("正常", "Base URL", base_url, "地址格式看起来正常。")

    if api_format == "thunderbit_extract":
        add("需确认", "模型", model or "extract", "Thunderbit 抽取接口是第三方网页抽取接口，不是通用聊天模型。")
    elif not model:
        add("错误", "模型", "未选择", "从模型下拉框选择一个模型，或直接粘贴服务商文档里的模型名。")
    elif provider == "openai" and model in {"gpt-5.2-pro"}:
        add("错误", "模型", model, "该模型仅支持 OpenAI Responses API；当前桌面版使用 Chat Completions，请改选 gpt-5.2 或 gpt-5-mini。")
    elif known_models and model not in known_models:
        add("需确认", "模型", model, "模型不在当前缓存/内置列表中；可点击“拉取模型”确认，或检查是否拼写错误。")
    else:
        add("正常", "模型", model, "模型名在当前可选列表中。")

    api_key_count = len(normalize_api_key_entries(settings.get("api_keys"), api_key, settings.get("active_api_key_name", "")))
    if not api_key and not base_url.startswith(("http://127.0.0.1", "http://localhost")):
        add("错误", "API Key", "未填写", "填写该服务商 API Key；本软件不走本地模型，AI 功能必须调用远程 API。")
    else:
        add("正常", "API Key", f"已选择 {mask_api_key(api_key)}；共 {api_key_count} 个" if api_key else "本地调试地址可为空", "API Key 只保存在本机配置文件。")

    if api_format == "thunderbit_extract":
        add("正常", "模型列表 URL", "不适用", "第三方抽取接口不按大模型列表拉取；动作名通常固定为 extract。")
    elif api_format == "gemini":
        expected_models_url = f"{base_url.rstrip('/')}/models" if base_url else preset.get("models_url", "")
        add("正常" if base_url else "需确认", "模型列表 URL", models_url or expected_models_url, "Gemini 会按 Base URL 自动访问 /models?key=API_KEY。")
    elif models_url:
        parsed = urlparse(models_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            add("错误", "模型列表 URL", models_url, "模型列表 URL 必须是完整 http/https 地址。")
        elif provider in AI_PROVIDER_PRESETS and preset.get("models_url") and models_url.rstrip("/") != preset.get("models_url", "").rstrip("/"):
            add("需确认", "模型列表 URL", models_url, f"与内置预设不同；默认地址是 {preset.get('models_url')}。")
        else:
            add("正常", "模型列表 URL", models_url, "可点击“拉取模型”更新在线模型缓存。")
    else:
        add("需确认", "模型列表 URL", "未填写", "该服务商可能不支持统一拉取模型；需要手动填写模型名。")

    if len(known_models) < 3 and api_format != "thunderbit_extract":
        add("需确认", "模型缓存", f"{len(known_models)} 个", "可点击“拉取模型”，或把常用模型名手动填入后保存。")
    else:
        add("正常", "模型缓存", f"{len(known_models)} 个", "当前服务商已有可选模型。")

    if any(row["level"] == "错误" for row in rows):
        summary = "发现必须修复的问题，建议先按表格里的“错误”项处理。"
    elif any(row["level"] == "需确认" for row in rows):
        summary = "没有发现硬性错误，但有配置项建议确认。"
    else:
        summary = "配置看起来正常，可以测试 API 或开始 AI 抽取。"
    return {"ok": not any(row["level"] == "错误" for row in rows), "summary": summary, "checks": rows}


def default_ai_settings():
    providers = {
        provider: default_provider_ai_settings(provider)
        for provider in AI_PROVIDER_PRESETS
    }
    settings = deepcopy(providers["openai"])
    settings["providers"] = providers
    return settings


def load_ai_settings(file_path=None):
    file_path = file_path or runtime_ai_settings_file()
    ensure_runtime_dirs()
    settings = default_ai_settings()
    if not os.path.exists(file_path):
        return settings
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return settings
    data = decrypt_ai_settings_from_disk(data)
    if isinstance(data, dict):
        providers = settings.get("providers", {})
        saved_providers = data.get("providers", {})
        if isinstance(saved_providers, dict):
            for provider_key, provider_data in saved_providers.items():
                if not isinstance(provider_data, dict):
                    continue
                provider_settings = providers.get(provider_key, default_provider_ai_settings(provider_key))
                providers[provider_key] = merge_provider_preset(provider_key, {**provider_settings, **provider_data})
        legacy_provider = data.get("provider") or settings.get("provider") or "openai"
        legacy_keys = {
            "provider",
            "provider_name",
            "api_format",
            "base_url",
            "models_url",
            "model",
            "models",
            "model_cache",
            "models_updated_at",
            "models_refresh_error",
            "connection_status",
            "connection_tested_at",
            "connection_error",
            "api_key",
            "api_keys",
            "active_api_key_name",
            "auto_apply_use_case",
            "temperature",
            "timeout_seconds",
        }
        legacy_values = {k: v for k, v in data.items() if k in legacy_keys}
        if legacy_values:
            provider_settings = providers.get(legacy_provider, default_provider_ai_settings(legacy_provider))
            providers[legacy_provider] = merge_provider_preset(legacy_provider, {**provider_settings, **legacy_values})
        settings["providers"] = providers
        provider = legacy_provider
        settings.update(providers.get(provider, default_provider_ai_settings(provider)))
    for provider_key, provider_settings in list(settings.get("providers", {}).items()):
        settings["providers"][provider_key] = merge_provider_preset(provider_key, provider_settings)
    provider = settings.get("provider") or "custom"
    if provider in AI_PROVIDER_PRESETS:
        settings.update(settings.get("providers", {}).get(provider, default_provider_ai_settings(provider)))
    return settings


def save_ai_settings(settings, file_path=None):
    file_path = file_path or runtime_ai_settings_file()
    ensure_runtime_dirs()
    current = load_ai_settings(file_path) if os.path.exists(file_path) else default_ai_settings()
    merged = deepcopy(current)
    incoming = settings or {}
    provider = incoming.get("provider") or merged.get("provider") or "openai"
    providers = merged.get("providers") or {}
    provider_settings = providers.get(provider, default_provider_ai_settings(provider))
    provider_settings.update(incoming)
    provider_settings["provider"] = provider
    if provider in AI_PROVIDER_PRESETS:
        provider_settings["provider_name"] = AI_PROVIDER_PRESETS[provider]["name"]
    if incoming.get("models") and not incoming.get("model_cache"):
        provider_settings["model_cache"] = list(incoming.get("models") or [])
    providers[provider] = provider_settings
    merged.update(provider_settings)
    merged["providers"] = providers
    temp_path = f"{file_path}.tmp.{os.getpid()}"
    disk_payload = encrypt_ai_settings_for_disk(merged)
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(disk_payload, f, ensure_ascii=False, indent=4)
    os.replace(temp_path, file_path)
    return merged


def ai_preset_for(provider):
    return deepcopy(AI_PROVIDER_PRESETS.get(provider, AI_PROVIDER_PRESETS["custom"]))


def extract_json_from_text(text):
    text = clean_text(text, 200000)
    if not text:
        raise ValueError("AI 没有返回内容。")
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S | re.I)
    candidates = [fenced.group(1)] if fenced else []
    candidates.append(text)
    for candidate in candidates:
        candidate = candidate.strip()
        try:
            return json.loads(candidate)
        except Exception:
            pass
        for opener, closer in (("{", "}"), ("[", "]")):
            start = candidate.find(opener)
            end = candidate.rfind(closer)
            if start >= 0 and end > start:
                try:
                    return json.loads(candidate[start : end + 1])
                except Exception:
                    continue
    raise ValueError("AI 返回的不是可解析 JSON。")


def page_snapshot_from_html(url, html):
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "canvas"]):
        tag.decompose()
    headings = []
    for tag in soup.select("h1, h2, h3")[:60]:
        text = compact_text(tag.get_text(" ", strip=True), 200)
        if text:
            headings.append({"tag": tag.name, "text": text})
    links = []
    for tag in soup.select("a[href]")[:120]:
        links.append(
            {
                "text": compact_text(tag.get_text(" ", strip=True), 160),
                "href": normalize_url(tag.get("href", ""), url),
            }
        )
    images = []
    for tag in soup.select("img")[:80]:
        images.append(
            {
                "alt": compact_text(tag.get("alt", ""), 160),
                "src": normalize_url(tag.get("src") or tag.get("data-src") or "", url),
            }
        )
    forms = []
    for tag in soup.select("input, textarea, select, button")[:120]:
        forms.append(
            {
                "tag": tag.name,
                "type": tag.get("type", ""),
                "name": tag.get("name", ""),
                "id": tag.get("id", ""),
                "placeholder": tag.get("placeholder", ""),
                "text": compact_text(tag.get_text(" ", strip=True), 100),
            }
        )
    text = clean_text(soup.get_text("\n", strip=True), AI_SNAPSHOT_TEXT_LIMIT)
    return {
        "url": url,
        "title": compact_text(soup.title.get_text(" ", strip=True), 300) if soup.title else "",
        "headings": headings,
        "links": links,
        "images": images,
        "forms": forms,
        "text": text,
    }


class AIClient:
    def __init__(self, settings=None):
        self.settings = load_ai_settings()
        self.settings.update(settings or {})

    @property
    def api_format(self):
        return (self.settings.get("api_format") or "openai_compatible").strip()

    @property
    def base_url(self):
        return (self.settings.get("base_url") or "").rstrip("/")

    @property
    def api_key(self):
        return (self.settings.get("api_key") or "").strip()

    @property
    def model(self):
        return (self.settings.get("model") or "").strip()

    def require_ready(self):
        if not self.base_url:
            raise RuntimeError("请先配置 API Base URL。")
        if not self.model and self.api_format != "thunderbit_extract":
            raise RuntimeError("请先选择或填写模型。")
        if not self.api_key and not self.base_url.startswith(("http://127.0.0.1", "http://localhost")):
            raise RuntimeError("请先填写 API Key。本软件不使用本地模型，AI 功能必须调用远程 API。")
        if self.settings.get("provider") == "openai" and self.model in {"gpt-5.2-pro"}:
            raise RuntimeError("gpt-5.2-pro 仅支持 OpenAI Responses API；当前桌面版请改选 gpt-5.2 或 gpt-5-mini。")

    def request_json(self, url, payload=None, headers=None, method="POST", timeout=None):
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers = {"Content-Type": "application/json"}
        request_headers.update(headers or {})
        request = Request(url, data=body, headers=request_headers, method=method)
        try:
            with urlopen(request, timeout=timeout or int(self.settings.get("timeout_seconds") or 60)) as response:
                data = response.read().decode("utf-8", errors="replace")
                return json.loads(data) if data else {}
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1200]
            raise RuntimeError(f"API 请求失败：HTTP {exc.code} {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"API 网络连接失败：{exc}") from exc

    def fetch_models(self):
        self.require_ready()
        api_format = self.api_format
        if api_format == "gemini":
            url = f"{self.base_url}/models?key={quote(self.api_key)}"
            data = self.request_json(url, method="GET", payload=None, headers={})
            models = [item.get("name", "").replace("models/", "") for item in data.get("models", [])]
            return [m for m in models if m]
        headers = {}
        if api_format == "anthropic":
            headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
        else:
            headers = {"Authorization": f"Bearer {self.api_key}"}
        models_url = (self.settings.get("models_url") or "").strip()
        if not models_url:
            raise RuntimeError("当前厂商没有可自动拉取模型的地址，请手动填写模型。")
        data = self.request_json(models_url, method="GET", payload=None, headers=headers)
        items = data.get("data") or data.get("models") or []
        models = []
        for item in items:
            if isinstance(item, str):
                models.append(item)
            elif isinstance(item, dict):
                models.append(item.get("id") or item.get("name") or item.get("model"))
        return [str(m).replace("models/", "") for m in models if m]

    def chat_text(self, system_prompt, user_prompt, images=None):
        self.require_ready()
        api_format = self.api_format
        if api_format == "thunderbit_extract":
            raise RuntimeError("Thunderbit Extract API 是第三方网页抽取接口，不是通用大模型对话接口。请切换到 OpenAI/Claude/Gemini/国内厂商模型。")
        if api_format == "anthropic":
            return self._chat_anthropic(system_prompt, user_prompt, images=images)
        if api_format == "gemini":
            return self._chat_gemini(system_prompt, user_prompt, images=images)
        return self._chat_openai_compatible(system_prompt, user_prompt, images=images)

    def chat_json(self, system_prompt, user_prompt, images=None):
        text = self.chat_text(
            system_prompt + "\n只返回 JSON，不要解释，不要 Markdown。",
            user_prompt,
            images=images,
        )
        return extract_json_from_text(text)

    def _image_parts_openai(self, images):
        parts = []
        for image_path in images or []:
            mime = mimetypes.guess_type(image_path)[0] or "image/png"
            with open(image_path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("ascii")
            parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{encoded}"},
                }
            )
        return parts

    def _image_parts_gemini(self, images):
        parts = []
        for image_path in images or []:
            mime = mimetypes.guess_type(image_path)[0] or "image/png"
            with open(image_path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("ascii")
            parts.append({"inline_data": {"mime_type": mime, "data": encoded}})
        return parts

    def _chat_openai_compatible(self, system_prompt, user_prompt, images=None):
        url = f"{self.base_url}/chat/completions"
        user_content = user_prompt
        if images:
            user_content = [{"type": "text", "text": user_prompt}] + self._image_parts_openai(images)
        payload = {
            "model": self.model,
            "temperature": float(self.settings.get("temperature") or 0.1),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        data = self.request_json(url, payload, headers)
        try:
            return data["choices"][0]["message"]["content"]
        except Exception as exc:
            raise RuntimeError(f"API 响应格式不符合 OpenAI 兼容格式：{data}") from exc

    def _chat_anthropic(self, system_prompt, user_prompt, images=None):
        if images:
            raise RuntimeError("当前桌面版暂未给 Claude 原生接口启用图片直传，请用 OpenAI 兼容或 Gemini 视觉模型处理图片。")
        url = f"{self.base_url}/v1/messages"
        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": float(self.settings.get("temperature") or 0.1),
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
        data = self.request_json(url, payload, headers)
        parts = data.get("content") or []
        return "\n".join(part.get("text", "") for part in parts if isinstance(part, dict))

    def _chat_gemini(self, system_prompt, user_prompt, images=None):
        url = f"{self.base_url}/models/{quote(self.model)}:generateContent?key={quote(self.api_key)}"
        parts = [{"text": system_prompt + "\n\n" + user_prompt}] + self._image_parts_gemini(images)
        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": float(self.settings.get("temperature") or 0.1)},
        }
        data = self.request_json(url, payload, headers={})
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as exc:
            raise RuntimeError(f"API 响应格式不符合 Gemini 格式：{data}") from exc

    def test_connection(self):
        result = self.chat_json(
            "你是连接测试器。",
            '返回 {"ok": true, "message": "连接成功"}',
        )
        if not result.get("ok"):
            raise RuntimeError(f"API 已响应，但没有返回 ok=true：{result}")
        return result


def ai_suggest_fields(url, html, user_goal="", settings=None):
    snapshot = page_snapshot_from_html(url, html)
    return AIClient(settings).chat_json(
        "你是网页数据提取专家，负责像 Thunderbit 的 AI Suggest Columns 一样为网页表格建议列。",
        json.dumps(
            {
                "task": "根据页面快照建议要提取的表格列。返回 fields 数组，每项包含 name, selector, attr, multiple, reason。selector 必须是可用于 BeautifulSoup/Playwright 的 CSS 选择器；attr 只能是 text/href/src/content/data-src。",
                "user_goal": user_goal,
                "snapshot": snapshot,
            },
            ensure_ascii=False,
        ),
    )


def ai_repair_fields(url, html, field_rules, quality_issues, user_goal="", settings=None):
    snapshot = page_snapshot_from_html(url, html)
    fields = [
        rule.to_dict() if hasattr(rule, "to_dict") else dict(rule)
        for rule in field_rules
    ]
    return AIClient(settings).chat_json(
        "你是网页字段修复专家，负责修复网页采集字段的 CSS 选择器问题。",
        json.dumps(
            {
                "task": "根据页面快照、当前字段和质量问题，返回修复后的 fields 数组。优先修复空值、重复、过长字段。每项包含 name, selector, attr, multiple, reason。不要返回无法执行的自然语言。",
                "user_goal": user_goal,
                "current_fields": fields,
                "quality_issues": quality_issues,
                "snapshot": snapshot,
            },
            ensure_ascii=False,
        ),
    )


def ai_parse_task(prompt, page_snapshot=None, settings=None):
    return AIClient(settings).chat_json(
        "你是桌面网页采集 Agent 规划器，必须把自然语言采集需求变成可执行配置。",
        json.dumps(
            {
                "task": "返回 JSON：template{name,domain,template_type,next_page_selector,field_rules[]}, options{use_browser,scroll_times,page_limit,subpage_limit}, actions[]。动作只允许 goto/click/fill/wait/scroll/extract/screenshot。",
                "prompt": prompt,
                "page_snapshot": page_snapshot or {},
            },
            ensure_ascii=False,
        ),
    )


def ai_transform_records(records, instruction, settings=None):
    compact_records = []
    for record in records[:200]:
        compact_records.append(
            {
                "url": record.get("url", ""),
                "title": record.get("title", ""),
                "price": record.get("price", ""),
                "time": record.get("published_time", ""),
                "author": record.get("author", ""),
                "body": compact_text(record.get("body", ""), 1200),
                "images": record.get("images", [])[:10],
                "links": record.get("links", [])[:20],
            }
        )
    return AIClient(settings).chat_json(
        "你是数据清洗助手，负责把网页采集结果加工成表格。",
        json.dumps(
            {
                "task": "按用户指令加工 records。返回 columns 数组和 rows 二维数组，可以新增摘要/分类/翻译/格式化字段。",
                "instruction": instruction,
                "records": compact_records,
            },
            ensure_ascii=False,
        ),
    )


def extract_text_from_pdf(file_path):
    try:
        from pypdf import PdfReader
    except Exception as exc:
        try:
            from PyPDF2 import PdfReader
        except Exception:
            raise RuntimeError("当前环境缺少 pypdf/PyPDF2，无法读取 PDF 文本；请安装 PDF 解析库或使用支持文件上传的视觉模型处理。") from exc
    reader = PdfReader(file_path)
    pages = []
    for page in reader.pages[:50]:
        pages.append(page.extract_text() or "")
    return clean_text("\n\n".join(pages), 50000)


def ai_extract_file_to_table(file_path, instruction="", settings=None):
    ext = os.path.splitext(file_path)[1].lower()
    client = AIClient(settings)
    if ext == ".pdf":
        text = extract_text_from_pdf(file_path)
        return client.chat_json(
            "你是 PDF 转表格数据提取器。",
            json.dumps(
                {
                    "task": "从 PDF 文本中提取结构化表格。返回 columns 数组和 rows 二维数组。",
                    "instruction": instruction,
                    "text": text,
                },
                ensure_ascii=False,
            ),
        )
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
        return client.chat_json(
            "你是图片/OCR 转表格数据提取器。",
            json.dumps(
                {
                    "task": "从图片中识别文字并提取结构化表格。返回 columns 数组和 rows 二维数组。",
                    "instruction": instruction,
                },
                ensure_ascii=False,
            ),
            images=[file_path],
        )
    with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
        text = f.read(50000)
    return client.chat_json(
        "你是文档转表格数据提取器。",
        json.dumps(
            {
                "task": "从文本中提取结构化表格。返回 columns 数组和 rows 二维数组。",
                "instruction": instruction,
                "text": text,
            },
            ensure_ascii=False,
        ),
    )


def extract_emails_and_phones(records):
    email_rows = []
    phone_rows = []
    seen_emails = set()
    seen_phones = set()
    phone_pattern = r"(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{4}"
    for record in records or []:
        title = clean_text(record.get("title", ""), 300)
        url = clean_text(record.get("url", ""), 1000)
        text = "\n".join(
            [
                str(record.get("title", "")),
                str(record.get("body", "")),
                list_to_text(record.get("links", [])),
            ]
        )
        for email in re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text):
            email_key = email.lower()
            if email_key in seen_emails:
                continue
            seen_emails.add(email_key)
            email_rows.append({"content": email, "type": "邮箱", "source_url": url, "source_title": title})
        for phone in re.findall(phone_pattern, text):
            normalized_phone = re.sub(r"\s+", " ", phone).strip()
            if normalized_phone in seen_phones:
                continue
            seen_phones.add(normalized_phone)
            phone_rows.append({"content": normalized_phone, "type": "电话", "source_url": url, "source_title": title})
    return {
        "emails": [item["content"] for item in email_rows],
        "phones": [item["content"] for item in phone_rows],
        "rows": email_rows + phone_rows,
    }


class DownloadedImage(dict):
    def __fspath__(self):
        return self.get("file_path", "")

    def __str__(self):
        return self.get("file_path", "")


def download_images_from_records(records, target_dir, logger=None):
    os.makedirs(target_dir, exist_ok=True)
    logger = logger or (lambda message: None)
    saved = []
    index = 1
    for record in records:
        source_url = clean_text(record.get("url", ""), 1000)
        source_title = clean_text(record.get("title", ""), 300)
        for image in record.get("images", []) or []:
            image_url = image.get("url", "") if isinstance(image, dict) else str(image)
            if not image_url:
                continue
            row = DownloadedImage(
                {
                    "status": "失败",
                    "image_url": image_url,
                    "file_path": "",
                    "source_url": source_url,
                    "source_title": source_title,
                    "error": "",
                }
            )
            try:
                request = Request(image_url, headers={"User-Agent": DEFAULT_USER_AGENT})
                with urlopen(request, timeout=20) as response:
                    data = response.read(20 * 1024 * 1024)
                    mime = response.headers.get_content_type()
            except Exception as exc:
                row["error"] = str(exc)
                logger(f"图片下载失败：{image_url} | {exc}")
                saved.append(row)
                continue
            ext = mimetypes.guess_extension(mime) or os.path.splitext(urlparse(image_url).path)[1] or ".jpg"
            file_path = os.path.join(target_dir, f"image_{index:04d}{ext}")
            with open(file_path, "wb") as f:
                f.write(data)
            row["status"] = "已保存"
            row["file_path"] = file_path
            row["mime"] = mime
            row["size_bytes"] = len(data)
            saved.append(row)
            index += 1
    return saved


class WebAgentExecutor:
    ALLOWED_ACTIONS = {"goto", "click", "fill", "wait", "scroll", "extract", "screenshot"}

    def __init__(self, logger=None):
        self.logger = logger or (lambda message: None)

    def execute(self, start_url, actions, keep_login_state=False, headless=True):
        from playwright.sync_api import sync_playwright

        records = []
        screenshots = []
        with sync_playwright() as p:
            if keep_login_state:
                os.makedirs(BROWSER_PROFILE_DIR, exist_ok=True)
                context = p.chromium.launch_persistent_context(
                    BROWSER_PROFILE_DIR,
                    headless=headless,
                    user_agent=DEFAULT_USER_AGENT,
                )
                page = context.pages[0] if context.pages else context.new_page()
                close_target = context
            else:
                browser = p.chromium.launch(headless=headless)
                page = browser.new_page(user_agent=DEFAULT_USER_AGENT)
                close_target = browser
            page.goto(start_url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT_SECONDS * 1000)
            for raw_action in actions or []:
                if not isinstance(raw_action, dict):
                    continue
                action = str(raw_action.get("type") or raw_action.get("action") or "").strip().lower()
                if action not in self.ALLOWED_ACTIONS:
                    self.logger(f"已跳过不支持动作：{action}")
                    continue
                selector = raw_action.get("selector") or ""
                value = raw_action.get("value") or raw_action.get("text") or ""
                self.logger(f"执行 Agent 动作：{action} {selector or value}")
                if action == "goto":
                    page.goto(normalize_url(value or raw_action.get("url") or start_url), wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT_SECONDS * 1000)
                elif action == "click" and selector:
                    page.locator(selector).first.click(timeout=8000)
                elif action == "fill" and selector:
                    page.locator(selector).first.fill(str(value), timeout=8000)
                elif action == "wait":
                    page.wait_for_timeout(int(raw_action.get("ms") or raw_action.get("milliseconds") or 1000))
                elif action == "scroll":
                    times = int(raw_action.get("times") or 1)
                    for _ in range(max(1, min(times, 50))):
                        page.mouse.wheel(0, int(raw_action.get("pixels") or 1600))
                        page.wait_for_timeout(400)
                elif action == "screenshot":
                    target = raw_action.get("path") or os.path.join(DATA_DIR, f"agent_screenshot_{int(time.time())}.png")
                    page.screenshot(path=target, full_page=True)
                    screenshots.append(target)
                elif action == "extract":
                    template = SiteTemplate(
                        name=raw_action.get("template_name") or "AI Agent 提取",
                        field_rules=[
                            FieldRule.from_dict(item)
                            for item in raw_action.get("field_rules", [])
                            if isinstance(item, dict)
                        ],
                    )
                    records.append(UniversalExtractor(template).extract(page.content(), page.url))
            close_target.close()
        return {"records": records, "screenshots": screenshots}


@dataclass
class FieldRule:
    name: str
    selector: str
    attr: str = "text"
    multiple: bool = False

    def to_dict(self):
        return {
            "name": self.name,
            "selector": self.selector,
            "attr": self.attr,
            "multiple": self.multiple,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            name=str(data.get("name", "")).strip(),
            selector=str(data.get("selector", "")).strip(),
            attr=str(data.get("attr", "text")).strip() or "text",
            multiple=bool(data.get("multiple", False)),
        )


@dataclass
class SiteTemplate:
    name: str
    domain: str = ""
    template_type: str = "auto"
    field_rules: list[FieldRule] = field(default_factory=list)
    next_page_selector: str = ""
    scroll_times: int = DEFAULT_SCROLL_TIMES
    notes: str = ""

    def to_dict(self):
        return {
            "name": self.name,
            "domain": self.domain,
            "template_type": self.template_type,
            "field_rules": [rule.to_dict() for rule in self.field_rules],
            "next_page_selector": self.next_page_selector,
            "scroll_times": self.scroll_times,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            name=str(data.get("name", "")).strip() or "未命名模板",
            domain=str(data.get("domain", "")).strip().lower(),
            template_type=str(data.get("template_type", "auto")).strip() or "auto",
            field_rules=[
                FieldRule.from_dict(rule)
                for rule in data.get("field_rules", [])
                if isinstance(rule, dict) and str(rule.get("name", "")).strip()
            ],
            next_page_selector=str(data.get("next_page_selector", "")).strip(),
            scroll_times=int(data.get("scroll_times", DEFAULT_SCROLL_TIMES) or 0),
            notes=str(data.get("notes", "")).strip(),
        )


def default_templates():
    return list(scene_template_presets().values())


def scene_template_presets():
    templates = [
        SiteTemplate(
            name="通用自动识别",
            template_type="auto",
            notes="自动提取标题、价格、图片、链接、时间、正文和表格。",
        ),
        SiteTemplate(
            name="电商商品页",
            template_type="ecommerce",
            field_rules=[
                FieldRule("标题", "h1, [class*=title], [id*=title]"),
                FieldRule("价格", "[class*=price], [id*=price], [class*=Price]"),
                FieldRule("正文", "main, article, [class*=description], [class*=detail], [class*=content]"),
                FieldRule("图片", "img", "src", True),
                FieldRule("链接", "a", "href", True),
            ],
            next_page_selector="a.next, .next, [class*=next], [rel=next]",
            notes="适合商品列表和商品详情页：标题、价格、详情、图片、链接。",
        ),
        SiteTemplate(
            name="新闻文章页",
            template_type="article",
            field_rules=[
                FieldRule("标题", "h1"),
                FieldRule("时间", "time, [class*=time], [class*=date], [id*=time]"),
                FieldRule("作者", "[class*=author], [class*=source], [id*=author]"),
                FieldRule("正文", "article, main, [class*=content], [id*=content]"),
            ],
            next_page_selector="a.next, .next, [class*=next], [rel=next]",
            notes="适合新闻、博客、公告：标题、发布时间、作者/来源、正文。",
        ),
        SiteTemplate(
            name="招聘职位页",
            template_type="jobs",
            field_rules=[
                FieldRule("标题", "h1, [class*=job], [class*=position]"),
                FieldRule("价格", "[class*=salary], [class*=pay], [class*=price]"),
                FieldRule("作者", "[class*=company], [id*=company]"),
                FieldRule("正文", "main, article, [class*=description], [class*=content]"),
            ],
            next_page_selector="a.next, .next, [class*=pagination], [rel=next]",
            notes="适合招聘网站：职位、薪资、公司、岗位描述。",
        ),
        SiteTemplate(
            name="企业黄页页",
            template_type="company",
            field_rules=[
                FieldRule("标题", "h1, [class*=company], [class*=name]"),
                FieldRule("作者", "[class*=contact], [class*=person]"),
                FieldRule("正文", "main, article, [class*=content], [class*=intro]"),
                FieldRule("链接", "a[href^=mailto], a[href^=tel], a", "href", True),
            ],
            notes="适合公司名录、B2B 黄页：公司名、联系人、简介、联系方式链接。",
        ),
        SiteTemplate(
            name="论坛帖子页",
            template_type="forum",
            field_rules=[
                FieldRule("标题", "h1, [class*=title]"),
                FieldRule("作者", "[class*=author], [class*=user], [class*=poster]"),
                FieldRule("时间", "time, [class*=time], [class*=date]"),
                FieldRule("正文", "article, main, [class*=post], [class*=content]"),
            ],
            next_page_selector="a.next, .next, [class*=next], [rel=next]",
            notes="适合论坛/社区/评论页：标题、用户、时间、帖子正文。",
        ),
        SiteTemplate(
            name="图片列表页",
            template_type="gallery",
            field_rules=[
                FieldRule("标题", "h1, title"),
                FieldRule("图片", "img", "src", True),
                FieldRule("链接", "a", "href", True),
            ],
            next_page_selector="a.next, .next, [class*=next], [rel=next]",
            notes="适合图片站、作品集、商品图列表：标题、图片、详情链接。",
        ),
        SiteTemplate(
            name="社媒内容页",
            template_type="forum",
            field_rules=[
                FieldRule("标题", "h1, [class*=title], [class*=caption]"),
                FieldRule("作者", "[class*=author], [class*=user], [class*=name], [class*=profile]"),
                FieldRule("时间", "time, [class*=time], [class*=date]"),
                FieldRule("正文", "article, main, [class*=post], [class*=content], [class*=caption]"),
                FieldRule("图片", "img", "src", True),
                FieldRule("链接", "a", "href", True),
            ],
            next_page_selector="a.next, .next, [class*=more], [class*=load]",
            notes="适合社媒公开内容、帖子流、评论流：作者、时间、正文、图片、链接。",
        ),
        SiteTemplate(
            name="房产房源页",
            template_type="real_estate",
            field_rules=[
                FieldRule("标题", "h1, [class*=title], [class*=house], [class*=name]"),
                FieldRule("价格", "[class*=price], [class*=rent], [class*=total]"),
                FieldRule("作者", "[class*=agent], [class*=broker], [class*=contact]"),
                FieldRule("正文", "main, article, [class*=detail], [class*=description], [class*=content]"),
                FieldRule("图片", "img", "src", True),
            ],
            next_page_selector="a.next, .next, [class*=pagination], [rel=next]",
            notes="适合租房/二手房/楼盘：房源标题、价格、经纪人、详情和图片。",
        ),
        SiteTemplate(
            name="本地服务页",
            template_type="local_service",
            field_rules=[
                FieldRule("标题", "h1, [class*=title], [class*=name]"),
                FieldRule("价格", "[class*=price], [class*=fee], [class*=cost]"),
                FieldRule("作者", "[class*=contact], [class*=phone], [class*=owner]"),
                FieldRule("正文", "main, article, [class*=service], [class*=content], [class*=intro]"),
                FieldRule("链接", "a[href^=tel], a[href^=mailto], a", "href", True),
            ],
            notes="适合维修、培训、医疗、本地商家：名称、价格/费用、联系人、介绍和联系方式。",
        ),
    ]
    return {template.name: template for template in templates}


def template_market_items():
    presets = scene_template_presets()
    items = [
        {
            "category": "电商/零售",
            "name": "电商商品页",
            "template": presets["电商商品页"],
            "keywords": "商品 价格 库存 SKU 产品 列表 详情 电商 店铺",
            "recommended_use_case": "cheap_batch",
        },
        {
            "category": "企业线索",
            "name": "企业黄页页",
            "template": presets["企业黄页页"],
            "keywords": "公司 企业 黄页 B2B 联系人 邮箱 电话 官网 客户",
            "recommended_use_case": "web_scrape",
        },
        {
            "category": "招聘/人才",
            "name": "招聘职位页",
            "template": presets["招聘职位页"],
            "keywords": "招聘 职位 薪资 公司 岗位 简历 Boss 拉勾 猎聘",
            "recommended_use_case": "cheap_batch",
        },
        {
            "category": "内容/媒体",
            "name": "新闻文章页",
            "template": presets["新闻文章页"],
            "keywords": "新闻 文章 博客 公告 媒体 时间 作者 来源",
            "recommended_use_case": "web_scrape",
        },
        {
            "category": "内容/媒体",
            "name": "论坛帖子页",
            "template": presets["论坛帖子页"],
            "keywords": "论坛 社区 帖子 评论 作者 回复 用户",
            "recommended_use_case": "web_scrape",
        },
        {
            "category": "图片/素材",
            "name": "图片列表页",
            "template": presets["图片列表页"],
            "keywords": "图片 相册 作品集 素材 壁纸 产品图 下载",
            "recommended_use_case": "vision_file",
        },
        {
            "category": "社媒/UGC",
            "name": "社媒内容页",
            "template": presets["社媒内容页"],
            "keywords": "社媒 公开内容 帖子流 评论流 作者 图片 链接",
            "recommended_use_case": "web_scrape",
        },
        {
            "category": "房产/本地",
            "name": "房产房源页",
            "template": presets["房产房源页"],
            "keywords": "房产 房源 租房 二手房 楼盘 小区 经纪人 户型",
            "recommended_use_case": "cheap_batch",
        },
        {
            "category": "房产/本地",
            "name": "本地服务页",
            "template": presets["本地服务页"],
            "keywords": "本地 服务 维修 培训 医疗 门店 地址 电话 预约",
            "recommended_use_case": "web_scrape",
        },
        {
            "category": "通用",
            "name": "通用自动识别",
            "template": presets["通用自动识别"],
            "keywords": "未知 通用 自动识别 任意网站 表格 链接 正文",
            "recommended_use_case": "web_scrape",
        },
    ]
    return [
        {
            **{key: value for key, value in item.items() if key != "template"},
            "template": deepcopy(item["template"]),
        }
        for item in items
    ]


def search_template_market(query="", category=""):
    query = compact_text(query or "", 500).lower()
    category = str(category or "").strip()
    matches = []
    for item in template_market_items():
        haystack = " ".join(
            [
                item.get("category", ""),
                item.get("name", ""),
                item.get("keywords", ""),
                item.get("template", SiteTemplate("")).notes,
            ]
        ).lower()
        if category and category != "全部分类" and item.get("category") != category:
            continue
        if query and query not in haystack:
            continue
        matches.append(item)
    return matches


def recommend_template_market_items(plan=None, url="", html="", user_goal="", limit=5):
    plan = plan if isinstance(plan, dict) else None
    if not plan:
        plan = analyze_collect_task(url, html=html, user_goal=user_goal)
    query_parts = [
        plan.get("template_name", ""),
        plan.get("template_type", ""),
        plan.get("page_kind", ""),
        user_goal or "",
        url or plan.get("url", ""),
    ]
    signals = plan.get("signals") or {}
    if signals.get("images", 0) >= 8:
        query_parts.append("图片")
    if signals.get("detail_like_links", 0) >= 2:
        query_parts.append("列表 详情")
    query = compact_text(" ".join(str(part or "") for part in query_parts), 2000).lower()
    scored = []
    for item in template_market_items():
        template = item.get("template") or SiteTemplate(item.get("name", ""))
        haystack = " ".join(
            [
                item.get("category", ""),
                item.get("name", ""),
                item.get("keywords", ""),
                template.template_type,
                template.notes,
            ]
        ).lower()
        score = 0
        if template.name == plan.get("template_name"):
            score += 100
        if template.template_type == plan.get("template_type"):
            score += 60
        for token in re.split(r"\s+", query):
            token = token.strip()
            if token and token in haystack:
                score += 6
        if item.get("recommended_use_case") == (plan.get("use_case") or {}).get("key"):
            score += 8
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {
            **item,
            "score": score,
            "reason": f"匹配 {item.get('name')}，页面类型 {plan.get('page_kind', '')}，模板类型 {plan.get('template_type', '')}",
        }
        for score, item in scored[: max(1, int(limit or 5))]
    ]


def recommended_use_case_for_task(page_kind="", template_type="", snapshot=None, url=""):
    snapshot = snapshot or {}
    text = compact_text(
        " ".join(
            [
                page_kind or "",
                template_type or "",
                snapshot.get("title", ""),
                snapshot.get("text", ""),
                url or "",
            ]
        ),
        8000,
    ).lower()
    path = urlparse(url or "").path.lower()
    images = snapshot.get("images", []) or []
    forms = snapshot.get("forms", []) or []
    if path.endswith((".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff")):
        return "vision_file"
    if page_kind in ("图片列表页",) or template_type == "gallery" or len(images) >= 10:
        return "vision_file"
    if page_kind == "列表页" or any(token in text for token in ("批量", "多页", "分页", "列表", "商品列表", "结果页")):
        return "cheap_batch"
    if page_kind in ("表单/搜索页",) or len(forms) >= 4 or any(token in text for token in ("修复", "复杂", "规则", "选择器", "动态", "登录")):
        return "strong_reasoning"
    return "web_scrape"


def analyze_collect_task(url, html="", user_goal="", preferred_scene=""):
    url = normalize_url(url)
    snapshot = page_snapshot_from_html(url, html or "")
    text = compact_text(" ".join([snapshot.get("title", ""), snapshot.get("text", ""), user_goal or ""]), 20000).lower()
    links = snapshot.get("links", []) or []
    images = snapshot.get("images", []) or []
    forms = snapshot.get("forms", []) or []
    tables_count = len(BeautifulSoup(html or "", "html.parser").select("table")) if html else 0
    link_count = len([item for item in links if item.get("href")])
    same_domain_links = [item for item in links if url_domain(item.get("href", "")) == url_domain(url)]
    detail_like_links = [
        item
        for item in same_domain_links
        if re.search(r"/(?:item|product|goods|detail|article|post|news|job|house|case)(?:[/-]|$)", item.get("href", "").lower())
        or re.search(r"[/=_-](?:\d{4,}|[a-f0-9]{8,})(?:[/?#]|$)", item.get("href", "").lower())
    ]
    next_candidates = []
    soup = BeautifulSoup(html or "", "html.parser")
    for selector in (
        "a[rel=next]",
        "a.next",
        ".next a",
        ".pagination a",
        "a[aria-label*=Next]",
        "a[aria-label*=下一页]",
    ):
        if html and soup.select_one(selector):
            next_candidates.append(selector)
    for link in links:
        label = f"{link.get('text', '')} {link.get('href', '')}".lower()
        if any(token in label for token in ("下一页", "next", "load more", "more", "更多")):
            next_candidates.append("a.next, .next, [rel=next], [class*=pagination] a")
            break

    keyword_groups = {
        "ecommerce": ("price", "cart", "sku", "stock", "buy", "shop", "商品", "产品", "价格", "库存", "购物车", "规格"),
        "jobs": ("salary", "job", "position", "resume", "职位", "招聘", "薪资", "简历", "岗位"),
        "real_estate": ("rent", "house", "estate", "bedroom", "房源", "租金", "户型", "小区", "楼盘"),
        "company": ("company", "contact", "email", "phone", "企业", "公司", "联系人", "邮箱", "电话", "官网"),
        "gallery": ("gallery", "photo", "album", "image", "图片", "相册", "作品", "壁纸"),
        "forum": ("comment", "reply", "post", "user", "评论", "回复", "帖子", "社区", "作者"),
        "article": ("article", "news", "blog", "author", "文章", "新闻", "博客", "发布时间", "来源"),
        "local_service": ("service", "booking", "address", "服务", "预约", "门店", "地址", "维修", "培训"),
    }
    scores = {key: 0 for key in keyword_groups}
    for key, tokens in keyword_groups.items():
        scores[key] += sum(8 for token in tokens if token in text)
    if len(images) >= 8:
        scores["gallery"] += 20
        scores["ecommerce"] += 8
    if tables_count:
        scores["auto"] = 10 + tables_count * 4
    if detail_like_links and link_count >= 12:
        scores["ecommerce"] += 10
        scores["forum"] += 5
    if any(item.get("tag") in ("input", "select", "textarea") for item in forms):
        scores["local_service"] += 6
        scores["company"] += 6
    preferred_type = ""
    presets = scene_template_presets()
    preferred = presets.get(preferred_scene or "")
    if preferred:
        preferred_type = preferred.template_type
        scores[preferred_type] = scores.get(preferred_type, 0) + 12
    template_type = max(scores, key=lambda key: scores.get(key, 0)) if scores else "auto"
    if scores.get(template_type, 0) <= 0:
        template_type = preferred_type or "auto"
    template_name = next(
        (item.name for item in presets.values() if item.template_type == template_type),
        preferred_scene or "通用自动识别",
    )
    preset = presets.get(template_name) or presets.get("通用自动识别")

    page_kind = "详情页"
    if len(detail_like_links) >= 2 or (detail_like_links and link_count >= 8):
        page_kind = "列表页"
    elif tables_count:
        page_kind = "表格页"
    elif len(images) >= 10 and len(images) > max(3, len(snapshot.get("headings", []))):
        page_kind = "图片列表页"
    elif len(forms) >= 6:
        page_kind = "表单/搜索页"
    elif template_type == "article":
        page_kind = "文章页"

    use_case_key = recommended_use_case_for_task(page_kind, template_type, snapshot, url)
    next_page_selector = next_candidates[0] if next_candidates else (preset.next_page_selector if page_kind == "列表页" else "")
    page_limit = 3 if next_page_selector else 1
    scroll_times = 4 if page_kind in ("列表页", "图片列表页") or len(images) >= 6 else 2
    subpage_limit = min(20, max(3, len(detail_like_links))) if page_kind == "列表页" and detail_like_links else 0
    use_browser = bool(forms or len(images) >= 6 or page_kind in ("列表页", "图片列表页"))

    actions = [
        {"type": "goto", "url": url, "note": "打开目标网页"},
    ]
    if scroll_times:
        actions.append({"type": "scroll", "times": scroll_times, "note": "加载动态内容或更多列表项"})
    if next_page_selector:
        actions.append({"type": "click", "selector": next_page_selector, "repeat": page_limit - 1, "note": "按下一页继续采集"})
    if subpage_limit:
        actions.append({"type": "extract", "scope": "same-domain detail links", "limit": subpage_limit, "note": "进入同站详情页补充数据"})
    actions.append({"type": "extract", "template_name": template_name, "note": "按推荐模板输出结构化表格"})

    recommendations = []
    if page_kind == "列表页":
        recommendations.append(f"建议开启子页面抓取，上限 {subpage_limit or 5}，用于补充详情页字段。")
    if next_page_selector:
        recommendations.append(f"检测到分页线索，可用下一页 CSS：{next_page_selector}")
    else:
        recommendations.append(f"未检测到明确下一页按钮，建议先按同页滚动 {scroll_times} 次预采。")
    if not html:
        recommendations.append("当前只基于网址和场景判断；预采页面后向导会更准。")
    if forms:
        recommendations.append("页面包含表单/筛选控件，必要时使用网页 Agent 或登录浏览器。")

    field_rules = [rule.to_dict() for rule in (preset.field_rules if preset else [])]
    return {
        "url": url,
        "page_kind": page_kind,
        "template_name": template_name,
        "template_type": template_type,
        "confidence": min(95, 45 + scores.get(template_type, 0) + (15 if html else 0)),
        "signals": {
            "links": link_count,
            "same_domain_links": len(same_domain_links),
            "detail_like_links": len(detail_like_links),
            "images": len(images),
            "forms": len(forms),
            "tables": tables_count,
            "next_page_candidates": list(dict.fromkeys(next_candidates))[:5],
        },
        "template": {
            "name": template_name,
            "domain": url_domain(url),
            "template_type": template_type,
            "next_page_selector": next_page_selector,
            "field_rules": field_rules,
        },
        "use_case": {
            "key": use_case_key,
            **AI_MODEL_USE_CASE_PRESETS.get(use_case_key, AI_MODEL_USE_CASE_PRESETS["web_scrape"]),
        },
        "options": {
            "use_browser": use_browser,
            "scroll_times": scroll_times,
            "page_limit": page_limit,
            "subpage_limit": subpage_limit,
        },
        "actions": actions,
        "recommendations": recommendations,
        "summary": f"{page_kind}｜推荐模板：{template_name}｜置信度：{min(95, 45 + scores.get(template_type, 0) + (15 if html else 0))}%",
    }


class TemplateStore:
    def __init__(self, file_path=None):
        self.file_path = file_path or runtime_template_file()

    def load(self):
        ensure_runtime_dirs()
        if not os.path.exists(self.file_path):
            templates = default_templates()
            self.save(templates)
            return templates
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            templates = default_templates()
            self.save(templates)
            return templates
        if not isinstance(data, list):
            return default_templates()
        templates = [
            SiteTemplate.from_dict(item)
            for item in data
            if isinstance(item, dict)
        ]
        return templates or default_templates()

    def save(self, templates):
        ensure_runtime_dirs()
        payload = [template.to_dict() for template in templates]
        temp_path = f"{self.file_path}.tmp.{os.getpid()}"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=4)
        os.replace(temp_path, self.file_path)

    def choose_for_url(self, url, preferred_name=""):
        templates = self.load()
        if preferred_name:
            for template in templates:
                if template.name == preferred_name:
                    return template
        domain = url_domain(url)
        for template in templates:
            if template.domain and template.domain in domain:
                return template
        return templates[0] if templates else SiteTemplate("通用自动识别")


class UniversalExtractor:
    def __init__(self, template: Optional[SiteTemplate] = None):
        self.template = template or SiteTemplate("通用自动识别")

    def extract(self, html, url):
        soup = BeautifulSoup(html or "", "html.parser")
        self.remove_noise(soup)
        record = {
            "collected_at": now_text(),
            "url": url,
            "domain": url_domain(url),
            "template_name": self.template.name,
            "title": self.extract_title(soup),
            "price": self.extract_price(soup),
            "published_time": self.extract_time(soup),
            "author": self.extract_author(soup),
            "body": self.extract_body(soup),
            "images": self.extract_images(soup, url),
            "links": self.extract_links(soup, url),
            "tables": self.extract_tables(soup),
            "error": "",
        }
        self.apply_template_rules(soup, url, record)
        record["fingerprint"] = content_fingerprint(record)
        return record

    def remove_noise(self, soup):
        for tag in soup(["script", "style", "noscript", "svg", "canvas"]):
            tag.decompose()

    def first_meta(self, soup, names):
        selectors = []
        for name in names:
            selectors.append(f'meta[property="{name}"]')
            selectors.append(f'meta[name="{name}"]')
            selectors.append(f'meta[itemprop="{name}"]')
        for selector in selectors:
            tag = soup.select_one(selector)
            if tag and tag.get("content"):
                return compact_text(tag.get("content"), 1000)
        return ""

    def extract_title(self, soup):
        for getter in (
            lambda: self.first_meta(soup, ["og:title", "twitter:title", "title"]),
            lambda: compact_text(soup.select_one("h1").get_text(" ", strip=True), 500)
            if soup.select_one("h1")
            else "",
            lambda: compact_text(soup.title.get_text(" ", strip=True), 500)
            if soup.title
            else "",
        ):
            value = getter()
            if value:
                return value
        return ""

    def extract_price(self, soup):
        meta_price = self.first_meta(
            soup,
            [
                "product:price:amount",
                "og:price:amount",
                "price",
                "sale_price",
                "lowPrice",
                "highPrice",
            ],
        )
        if meta_price:
            return meta_price
        selectors = [
            "[class*=price]",
            "[id*=price]",
            "[class*=Price]",
            "[data-price]",
            "[itemprop=price]",
        ]
        for selector in selectors:
            for tag in soup.select(selector)[:20]:
                text = compact_text(tag.get("data-price") or tag.get_text(" ", strip=True), 120)
                price = self.price_from_text(text)
                if price:
                    return price
        return self.price_from_text(soup.get_text(" ", strip=True)[:5000])

    def price_from_text(self, text):
        match = re.search(
            r"((?:¥|￥|\$|USD|CNY|RMB)?\s*\d{1,7}(?:,\d{3})*(?:\.\d{1,2})?\s*(?:元|块|美元)?)",
            text or "",
            re.I,
        )
        return compact_text(match.group(1), 80) if match else ""

    def extract_time(self, soup):
        meta_time = self.first_meta(
            soup,
            [
                "article:published_time",
                "publishdate",
                "pubdate",
                "date",
                "datePublished",
                "og:updated_time",
            ],
        )
        if meta_time:
            return meta_time
        for tag in soup.select("time, [class*=time], [class*=date], [id*=time], [id*=date]")[:30]:
            value = compact_text(tag.get("datetime") or tag.get_text(" ", strip=True), 120)
            if self.looks_like_time(value):
                return value
        text = soup.get_text(" ", strip=True)[:8000]
        match = re.search(
            r"\d{4}[-/年.]\d{1,2}[-/月.]\d{1,2}(?:日)?(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?",
            text,
        )
        return match.group(0) if match else ""

    def looks_like_time(self, value):
        return bool(re.search(r"\d{4}|\d{1,2}:\d{2}|昨天|今天|前|发布", value or ""))

    def extract_author(self, soup):
        meta_author = self.first_meta(soup, ["author", "article:author", "byl"])
        if meta_author:
            return meta_author
        for selector in (
            "[class*=author]",
            "[id*=author]",
            "[class*=source]",
            "[class*=user]",
            "[class*=seller]",
            "[class*=company]",
            "[itemprop=author]",
        ):
            tag = soup.select_one(selector)
            if tag:
                value = compact_text(tag.get_text(" ", strip=True), 200)
                if value:
                    return value
        return ""

    def extract_body(self, soup):
        candidates = []
        for selector in (
            "article",
            "main",
            "[role=main]",
            "[class*=content]",
            "[id*=content]",
            "[class*=article]",
            "[class*=detail]",
            "[class*=description]",
        ):
            for tag in soup.select(selector)[:10]:
                text = clean_text(tag.get_text("\n", strip=True))
                if len(text) > 80:
                    candidates.append(text)
        if not candidates:
            paragraphs = [
                clean_text(tag.get_text(" ", strip=True), 1000)
                for tag in soup.select("p")
            ]
            candidates = [text for text in paragraphs if len(text) > 20]
        if not candidates:
            return clean_text(soup.get_text("\n", strip=True), 6000)
        return max(candidates, key=len)

    def extract_images(self, soup, url):
        images = []
        for img in soup.select("img"):
            src = img.get("src") or img.get("data-src") or img.get("data-original")
            src = normalize_url(src, url)
            if not src or src.startswith("data:"):
                continue
            item = {
                "url": src,
                "alt": compact_text(img.get("alt", ""), 300),
            }
            if item not in images:
                images.append(item)
            if len(images) >= MAX_IMAGES:
                break
        return images

    def extract_links(self, soup, url):
        links = []
        seen = set()
        for link in soup.select("a[href]"):
            href = normalize_url(link.get("href"), url)
            if not href or href.startswith(("javascript:", "mailto:", "tel:")):
                continue
            text = compact_text(link.get_text(" ", strip=True), 300)
            key = (href, text)
            if key in seen:
                continue
            seen.add(key)
            links.append({"url": href, "text": text})
            if len(links) >= MAX_LINKS:
                break
        return links

    def extract_tables(self, soup):
        tables = []
        for table in soup.select("table")[:20]:
            rows = []
            for tr in table.select("tr")[:MAX_TABLE_ROWS]:
                cells = [
                    compact_text(cell.get_text(" ", strip=True), 500)
                    for cell in tr.select("th, td")
                ]
                if any(cells):
                    rows.append(cells)
            if rows:
                tables.append(rows)
        return tables

    def apply_template_rules(self, soup, url, record):
        aliases = {
            "标题": "title",
            "价格": "price",
            "时间": "published_time",
            "作者": "author",
            "正文": "body",
            "图片": "images",
            "链接": "links",
            "表格": "tables",
        }
        custom_fields = {}
        for rule in self.template.field_rules:
            if not rule.selector:
                continue
            value = self.extract_by_rule(soup, url, rule)
            key = aliases.get(rule.name, rule.name)
            if key in record:
                if value:
                    if key == "images":
                        value = self.normalize_image_values(value, url)
                    elif key == "links":
                        value = self.normalize_link_values(value, url)
                    record[key] = value
            else:
                custom_fields[rule.name] = value
        if custom_fields:
            extra = "\n\n自定义字段：\n" + json.dumps(custom_fields, ensure_ascii=False, indent=2)
            record["body"] = clean_text((record.get("body") or "") + extra)

    def extract_by_rule(self, soup, url, rule):
        items = []
        for tag in soup.select(rule.selector):
            if rule.attr == "text":
                value = compact_text(tag.get_text(" ", strip=True), 3000)
            else:
                value = normalize_url(tag.get(rule.attr, ""), url)
            if value:
                items.append(value)
            if not rule.multiple:
                break
        if rule.multiple:
            return list(dict.fromkeys(items))
        return items[0] if items else ""

    def normalize_image_values(self, value, url):
        values = value if isinstance(value, list) else [value]
        images = []
        for item in values:
            if isinstance(item, dict):
                image_url = normalize_url(item.get("url", ""), url)
                alt = compact_text(item.get("alt", ""), 300)
            else:
                image_url = normalize_url(item, url)
                alt = ""
            if image_url and not image_url.startswith("data:"):
                images.append({"url": image_url, "alt": alt})
        return images

    def normalize_link_values(self, value, url):
        values = value if isinstance(value, list) else [value]
        links = []
        for item in values:
            if isinstance(item, dict):
                link_url = normalize_url(item.get("url", ""), url)
                text = compact_text(item.get("text", ""), 300)
            else:
                link_url = normalize_url(item, url)
                text = ""
            if link_url:
                links.append({"url": link_url, "text": text})
        return links


class UniversalCollector:
    def __init__(
        self,
        template_store: Optional[TemplateStore] = None,
        database: Optional[CollectorDatabase] = None,
        logger: Optional[Callable[[str], None]] = None,
    ):
        self.template_store = template_store or TemplateStore()
        self.database = database or CollectorDatabase()
        self.logger = logger or (lambda message: None)

    def log(self, message):
        self.logger(message)

    def collect_urls(
        self,
        urls: Iterable[str],
        template_name="",
        use_browser=True,
        scroll_times=DEFAULT_SCROLL_TIMES,
        page_limit=1,
        delay_seconds=0.5,
        keep_login_state=False,
        skip_unchanged=True,
        scrape_subpages=False,
        subpage_limit=0,
        selected_subpage_urls=None,
        stop_requested: Optional[Callable[[], bool]] = None,
        run_id=0,
        progress_callback: Optional[Callable[[dict], None]] = None,
    ):
        urls = list(urls or [])
        results = []
        visited = set()
        progress = {
            "processed": 0,
            "success": 0,
            "failed": 0,
            "total": len([item for item in urls if normalize_url(item)]),
            "current_url": "",
            "stage": "准备采集",
        }

        def emit_progress(stage, current_url="", increment=False, failed=False):
            progress["current_failed"] = bool(failed)
            progress["failed_item"] = bool(failed and increment)
            if increment:
                progress["processed"] += 1
                if failed:
                    progress["failed"] += 1
                else:
                    progress["success"] += 1
            if current_url:
                progress["current_url"] = current_url
            progress["stage"] = stage
            if progress_callback:
                try:
                    progress_callback(dict(progress))
                except Exception:
                    pass

        selected_subpages = []
        for item in selected_subpage_urls or []:
            normalized = normalize_url(item)
            if normalized and normalized not in selected_subpages:
                selected_subpages.append(normalized)
        emit_progress("准备采集")
        for raw_url in urls:
            if stop_requested and stop_requested():
                break
            url = normalize_url(raw_url)
            if not url:
                continue
            emit_progress("选择模板", url)
            visited.add(url)
            template = self.template_store.choose_for_url(url, template_name)
            template.scroll_times = scroll_times
            target_urls = [url]
            if page_limit > 1:
                emit_progress("展开分页", url)
                target_urls = self.expand_pages(
                    url,
                    template,
                    use_browser,
                    page_limit,
                    keep_login_state=keep_login_state,
                )
                progress["total"] = max(progress["total"], progress["processed"] + len(target_urls))
                emit_progress("分页完成", target_urls[-1] if target_urls else url)
            for target_url in target_urls:
                if stop_requested and stop_requested():
                    break
                emit_progress("采集页面", target_url)
                record = self.collect_one(
                    target_url,
                    template,
                    use_browser,
                    scroll_times,
                    keep_login_state=keep_login_state,
                )
                record["run_id"] = int(run_id or 0)
                self.database.save_record(record, skip_unchanged=skip_unchanged)
                results.append(record)
                emit_progress("页面完成", target_url, increment=True, failed=bool(record.get("error")))
                if selected_subpages:
                    emit_progress("准备已选子页面", target_url)
                    subpages = self.selected_subpage_urls_for_parent(selected_subpages, target_url, visited)
                elif scrape_subpages and int(subpage_limit or 0) > 0:
                    emit_progress("扫描子页面", target_url)
                    subpages = self.subpage_urls_from_record(record, target_url, int(subpage_limit), visited)
                else:
                    subpages = []
                if subpages:
                    progress["total"] = max(progress["total"], progress["processed"] + len(subpages))
                    emit_progress("子页面待采集", subpages[0])
                if subpages:
                    for subpage_url in subpages:
                        if stop_requested and stop_requested():
                            break
                        emit_progress("采集子页面", subpage_url)
                        sub_record = self.collect_one(
                            subpage_url,
                            template,
                            use_browser,
                            scroll_times,
                            keep_login_state=keep_login_state,
                        )
                        sub_record["run_id"] = int(run_id or 0)
                        self.database.save_record(sub_record, skip_unchanged=skip_unchanged)
                        results.append(sub_record)
                        emit_progress("子页面完成", subpage_url, increment=True, failed=bool(sub_record.get("error")))
                        visited.add(subpage_url)
                        if delay_seconds > 0:
                            time.sleep(delay_seconds)
                if delay_seconds > 0:
                    time.sleep(delay_seconds)
        emit_progress("采集结束")
        return results

    def selected_subpage_urls_for_parent(self, selected_subpages, parent_url, visited):
        parent_domain = url_domain(parent_url)
        urls = []
        for raw_url in selected_subpages:
            link_url = normalize_url(raw_url, parent_url)
            if not link_url or link_url in visited:
                continue
            if url_domain(link_url) != parent_domain:
                continue
            if any(token in link_url.lower() for token in ("#", "javascript:", "mailto:", "tel:")):
                continue
            urls.append(link_url)
            visited.add(link_url)
        if urls:
            self.log(f"使用已选择的 {len(urls)} 个子页面进行深度采集。")
        return urls

    def subpage_urls_from_record(self, record, parent_url, limit, visited):
        parent_domain = url_domain(parent_url)
        urls = []
        for link in record.get("links", []) or []:
            link_url = link.get("url", "") if isinstance(link, dict) else str(link)
            link_url = normalize_url(link_url, parent_url)
            if not link_url or link_url in visited:
                continue
            if url_domain(link_url) != parent_domain:
                continue
            if any(token in link_url.lower() for token in ("#", "javascript:", "mailto:", "tel:")):
                continue
            urls.append(link_url)
            visited.add(link_url)
            if len(urls) >= limit:
                break
        if urls:
            self.log(f"发现 {len(urls)} 个子页面，开始深度采集。")
        return urls

    def scan_subpage_links(
        self,
        url,
        use_browser=True,
        scroll_times=DEFAULT_SCROLL_TIMES,
        keep_login_state=False,
        limit=120,
    ):
        html = (
            self.fetch_with_playwright(
                url,
                scroll_times=scroll_times,
                keep_login_state=keep_login_state,
            )
            if use_browser
            else self.fetch_static(url)
        )
        record = UniversalExtractor(SiteTemplate("链接扫描")).extract(html, url)
        return self.rank_subpage_links(record.get("links", []) or [], url, limit=limit)

    def rank_subpage_links(self, links, parent_url, limit=120):
        parent_domain = url_domain(parent_url)
        candidates = []
        seen = set()
        for link in links:
            raw_url = link.get("url", "") if isinstance(link, dict) else str(link)
            text = link.get("text", "") if isinstance(link, dict) else ""
            link_url = normalize_url(raw_url, parent_url)
            if not link_url or link_url in seen:
                continue
            seen.add(link_url)
            parsed = urlparse(link_url)
            scheme = parsed.scheme.lower()
            if scheme not in ("http", "https"):
                continue
            if any(token in link_url.lower() for token in ("javascript:", "mailto:", "tel:")):
                continue
            same_domain = url_domain(link_url) == parent_domain
            score, link_type, reason = self.score_subpage_link(link_url, text, same_domain)
            candidates.append(
                {
                    "selected": bool(same_domain and score >= 25),
                    "text": compact_text(text or parsed.path.strip("/") or parsed.netloc, 160),
                    "url": link_url,
                    "domain": url_domain(link_url),
                    "type": link_type,
                    "reason": reason,
                    "score": score,
                    "same_domain": same_domain,
                }
            )
        candidates.sort(key=lambda item: (not item.get("selected"), -int(item.get("score", 0)), item.get("url", "")))
        return candidates[: max(1, int(limit or 120))]

    def score_subpage_link(self, link_url, text, same_domain):
        lower_url = link_url.lower()
        lower_text = (text or "").lower()
        score = 0
        reasons = []
        link_type = "普通链接"
        if same_domain:
            score += 35
            reasons.append("同站链接")
        else:
            score -= 80
            reasons.append("站外链接，默认不深抓")
            link_type = "站外链接"
        positive_tokens = {
            "detail": "详情页",
            "item": "详情页",
            "product": "商品页",
            "goods": "商品页",
            "sku": "商品页",
            "post": "文章/帖子",
            "article": "文章/帖子",
            "news": "文章/帖子",
            "company": "公司页",
            "profile": "资料页",
            "job": "职位页",
            "case": "案例页",
            "详情": "详情页",
            "商品": "商品页",
            "产品": "商品页",
            "文章": "文章/帖子",
            "新闻": "文章/帖子",
            "公司": "公司页",
            "职位": "职位页",
            "案例": "案例页",
        }
        for token, token_type in positive_tokens.items():
            if token in lower_url or token in lower_text:
                score += 18
                link_type = token_type
                reasons.append(f"疑似{token_type}")
                break
        negative_tokens = (
            "login",
            "signin",
            "register",
            "cart",
            "checkout",
            "privacy",
            "terms",
            "help",
            "about",
            "contact",
            "登录",
            "注册",
            "购物车",
            "隐私",
            "条款",
            "帮助",
            "关于",
            "联系",
        )
        if any(token in lower_url or token in lower_text for token in negative_tokens):
            score -= 35
            reasons.append("更像导航/账户/说明页")
            if link_type == "普通链接":
                link_type = "导航页"
        path_parts = [part for part in urlparse(link_url).path.split("/") if part]
        if len(path_parts) >= 2:
            score += 8
            reasons.append("路径较深")
        if re.search(r"[/=_-](\d{4,}|[a-f0-9]{8,})(?:[/?#]|$)", lower_url):
            score += 10
            reasons.append("URL 含详情编号")
        if len(text or "") > 80:
            score -= 10
            reasons.append("链接文字过长")
        return score, link_type, "；".join(dict.fromkeys(reasons)) or "可手动确认"

    def collect_one(
        self,
        url,
        template,
        use_browser=True,
        scroll_times=DEFAULT_SCROLL_TIMES,
        keep_login_state=False,
    ):
        self.log(f"开始采集：{url}")
        try:
            try:
                html = (
                    self.fetch_with_playwright(
                        url,
                        scroll_times=scroll_times,
                        keep_login_state=keep_login_state,
                    )
                    if use_browser
                    else self.fetch_static(url)
                )
            except Exception as browser_exc:
                if not use_browser:
                    raise
                self.log(f"浏览器采集失败，自动改用普通网页读取：{browser_exc}")
                html = self.fetch_static(url)
            record = UniversalExtractor(template).extract(html, url)
            self.log(f"采集完成：{compact_text(record.get('title') or url, 80)}")
            return record
        except Exception as exc:
            self.log(f"采集失败：{url} | {exc}")
            record = {
                "collected_at": now_text(),
                "url": url,
                "domain": url_domain(url),
                "template_name": template.name,
                "title": "",
                "price": "",
                "published_time": "",
                "author": "",
                "body": "",
                "images": [],
                "links": [],
                "tables": [],
                "error": str(exc),
            }
            record["fingerprint"] = content_fingerprint(record)
            return record

    def fetch_static(self, url):
        request = Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
        with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            data = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
        return data.decode(charset, errors="replace")

    def fetch_with_playwright(
        self,
        url,
        scroll_times=DEFAULT_SCROLL_TIMES,
        keep_login_state=False,
        headless=True,
    ):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            if keep_login_state:
                os.makedirs(BROWSER_PROFILE_DIR, exist_ok=True)
                context = p.chromium.launch_persistent_context(
                    BROWSER_PROFILE_DIR,
                    headless=headless,
                    user_agent=DEFAULT_USER_AGENT,
                )
                page = context.pages[0] if context.pages else context.new_page()
                close_target = context
            else:
                browser = p.chromium.launch(headless=headless)
                page = browser.new_page(user_agent=DEFAULT_USER_AGENT)
                close_target = browser
            self.prepare_dynamic_page(page, url, scroll_times)
            html = page.content()
            close_target.close()
        return html

    def prepare_dynamic_page(self, page, url, scroll_times=DEFAULT_SCROLL_TIMES):
        page.goto(url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT_SECONDS * 1000)
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        for _ in range(max(0, int(scroll_times))):
            page.mouse.wheel(0, 1600)
            page.wait_for_timeout(600)

    def open_login_browser(self, url="https://example.com/"):
        from playwright.sync_api import sync_playwright

        os.makedirs(BROWSER_PROFILE_DIR, exist_ok=True)
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                BROWSER_PROFILE_DIR,
                headless=False,
                user_agent=DEFAULT_USER_AGENT,
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT_SECONDS * 1000)
            return True

    def expand_pages(self, url, template, use_browser, page_limit, keep_login_state=False):
        page_limit = max(1, min(int(page_limit or 1), 50))
        if page_limit <= 1:
            return [url]
        if template.next_page_selector and use_browser:
            return self.expand_pages_by_click(
                url,
                template,
                page_limit,
                keep_login_state=keep_login_state,
            )
        return [url]

    def preview_pagination(
        self,
        url,
        next_page_selector="",
        page_limit=DEFAULT_PAGE_LIMIT,
        scroll_times=DEFAULT_SCROLL_TIMES,
        keep_login_state=False,
    ):
        template = SiteTemplate(
            "分页预览",
            next_page_selector=str(next_page_selector or "").strip(),
        )
        page_limit = max(1, min(int(page_limit or 1), 50))
        scroll_times = max(0, min(int(scroll_times or 0), 20))
        if template.next_page_selector:
            urls = self.expand_pages_by_click(
                url,
                template,
                page_limit,
                keep_login_state=keep_login_state,
            )
            mode = "点击下一页"
        else:
            urls = [normalize_url(url)]
            mode = "无限滚动"
        rows = []
        for index, page_url in enumerate(urls, start=1):
            rows.append(
                {
                    "page": index,
                    "url": page_url,
                    "mode": mode,
                    "scroll_times": scroll_times,
                    "status": "将采集",
                }
            )
        if mode == "无限滚动":
            rows[0]["status"] = f"同页滚动 {scroll_times} 次后采集"
        return {
            "mode": mode,
            "page_limit": page_limit,
            "scroll_times": scroll_times,
            "next_page_selector": template.next_page_selector,
            "urls": urls,
            "rows": rows,
        }

    def expand_pages_by_click(self, url, template, page_limit, keep_login_state=False):
        from playwright.sync_api import sync_playwright

        urls = []
        with sync_playwright() as p:
            if keep_login_state:
                os.makedirs(BROWSER_PROFILE_DIR, exist_ok=True)
                context = p.chromium.launch_persistent_context(
                    BROWSER_PROFILE_DIR,
                    headless=True,
                    user_agent=DEFAULT_USER_AGENT,
                )
                page = context.pages[0] if context.pages else context.new_page()
                close_target = context
            else:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(user_agent=DEFAULT_USER_AGENT)
                close_target = browser
            page.goto(url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT_SECONDS * 1000)
            for _ in range(page_limit):
                current = page.url
                if current not in urls:
                    urls.append(current)
                locator = page.locator(template.next_page_selector).first
                if not locator.count():
                    break
                try:
                    locator.click(timeout=5000)
                    page.wait_for_load_state("domcontentloaded", timeout=8000)
                    page.wait_for_timeout(800)
                except Exception:
                    break
            close_target.close()
        return urls


def build_selector_from_clicked_element(tag_name, element_id="", classes=None, text=""):
    tag_name = re.sub(r"[^a-zA-Z0-9_-]", "", tag_name or "").lower() or "*"
    element_id = re.sub(r"[^a-zA-Z0-9_-]", "", element_id or "")
    if element_id:
        return f"{tag_name}#{element_id}"
    classes = classes or []
    clean_classes = [
        re.sub(r"[^a-zA-Z0-9_-]", "", item)
        for item in classes
        if re.sub(r"[^a-zA-Z0-9_-]", "", item)
    ]
    if clean_classes:
        return tag_name + "".join(f".{item}" for item in clean_classes[:3])
    return tag_name
