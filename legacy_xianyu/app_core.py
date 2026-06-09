import csv
import json
import importlib.util
import os
import random
import re
import socket
import subprocess
import sys
import time
import traceback
from urllib.parse import parse_qsl, quote_plus, urlencode, urlparse, urlunparse
from urllib.request import urlopen

APP_VERSION = "2026.06.08-ui2"

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from PyQt6.QtCore import Qt, QObject, QThread, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QDesktopServices, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QCheckBox,
    QFrame,
    QFileDialog,
    QSizePolicy,
    QStyle,
    QScrollArea,
    QSplitter,
    QSpinBox,
    QStackedWidget,
    QSystemTrayIcon,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolBox,
    QVBoxLayout,
    QWidget,
)

from .cache_tools import clear_chrome_cache as remove_chrome_cache
from .cache_tools import chrome_cache_targets
from .notifications import create_notifier
from .process_tools import (
    SingleInstanceLock,
    is_owned_debug_chrome,
    other_monitor_processes,
    signal_existing_window,
)
from .storage import HitStore


APP_NAME_EN = "XianyuMonitor"
APP_NAME_CN = "闲鱼监测软件"
DEFAULT_CDP_HOST = "127.0.0.1"


def app_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def default_data_dir():
    if os.environ.get("XIANYU_MONITOR_SELF_TEST") == "1":
        return os.path.abspath(os.environ.get("XIANYU_MONITOR_SELF_TEST_DIR", "self_test_runtime"))
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return os.path.join(local_app_data, APP_NAME_EN)
    return os.path.join(app_base_dir(), "data")


DATA_DIR = os.path.abspath(os.environ.get("XIANYU_MONITOR_DATA_DIR", default_data_dir()))


def runtime_path(env_name, file_name):
    override = os.environ.get(env_name)
    if override:
        return os.path.abspath(override)
    return os.path.join(DATA_DIR, file_name)


def ensure_runtime_dirs():
    for directory in {
        DATA_DIR,
        os.path.dirname(os.path.abspath(CHROME_PROFILE_DIR)),
    }:
        if directory:
            os.makedirs(directory, exist_ok=True)


def find_free_tcp_port(host=DEFAULT_CDP_HOST):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


def cdp_endpoint(port, host=DEFAULT_CDP_HOST):
    return f"http://{host}:{int(port)}"


DB_FILE = runtime_path("XIANYU_MONITOR_DB_FILE", "scanned_items.json")
SMART_RULES_FILE = runtime_path("XIANYU_MONITOR_SMART_RULES_FILE", "smart_rules.json")
ITEM_STATUS_FILE = runtime_path("XIANYU_MONITOR_ITEM_STATUS_FILE", "item_statuses.json")
APP_SETTINGS_FILE = runtime_path("XIANYU_MONITOR_SETTINGS_FILE", "app_settings.json")
HIT_HISTORY_FILE = runtime_path("XIANYU_MONITOR_HIT_HISTORY_FILE", "hit_history.json")
APP_LOG_FILE = runtime_path("XIANYU_MONITOR_LOG_FILE", "monitor_log.txt")
STARTUP_LOG_FILE = runtime_path("XIANYU_MONITOR_STARTUP_LOG_FILE", "startup_error.log")
SELF_TEST_ERROR_LOG_FILE = runtime_path("XIANYU_MONITOR_SELF_TEST_ERROR_LOG_FILE", "self_test_error.log")
CHROME_PROFILE_DIR = runtime_path("XIANYU_MONITOR_CHROME_PROFILE_DIR", "chrome-profile")
CHROME_SESSION_FILE = runtime_path("XIANYU_MONITOR_CHROME_SESSION_FILE", "chrome_session.json")
CDP_ENDPOINTS = []
SEARCH_URL_TEMPLATES = [
    "https://www.goofish.com/search?q={query}",
]
PLATFORM_CONFIGS = {
    "xianyu": {
        "name": "闲鱼",
        "search_url_templates": ["https://www.goofish.com/search?q={query}"],
        "item_selectors": [
            'a[href*="goofish.com/item?id="]',
            'a[href*="/item?id="]',
            'div[class*="item-card"]',
            'div[class*="SearchList--item"]',
        ],
        "base_url": "https://www.goofish.com",
    },
    "jd": {
        "name": "京东",
        "search_url_templates": [
            "https://search.jd.com/Search?keyword={query}&enc=utf-8"
        ],
        "item_selectors": [
            "div.plugin_goodsCardWrapper",
            'div[class*="plugin_goodsCardWrapper"]',
            'div[class*="goodsCardWrapper"]',
            'div[class*="goodsContainer"]',
            'div[class*="goods-card"]',
            "[data-sku]",
            "li.gl-item",
            'li[class*="gl-item"]',
            "div.gl-i-wrap",
            'div[class*="gl-i-wrap"]',
            'a[href*="item.jd.com"]',
            'a[href*="//item.jd.com"]',
        ],
        "base_url": "https://search.jd.com",
    },
    "taobao": {
        "name": "淘宝",
        "search_url_templates": ["https://s.taobao.com/search?q={query}"],
        "item_selectors": [
            'a[id^="item_id_"]',
            'a[class*="doubleCardWrapper"]',
            'div[class*="search-content-col"]',
            'a[href*="item.taobao.com/item.htm"]',
            'a[href*="detail.tmall.com/item.htm"]',
            'div[class*="item"]',
        ],
        "base_url": "https://s.taobao.com",
    },
}
CHROME_EXE_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]
CHROME_DEBUG_COMMAND = (
    '"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" '
    "--remote-debugging-port=<动态端口> "
    f'--user-data-dir="{CHROME_PROFILE_DIR}"'
)
REQUIRED_DEPENDENCIES = [
    ("PyQt6", "PyQt6"),
    ("playwright", "playwright"),
    ("beautifulsoup4", "bs4"),
    ("openpyxl", "openpyxl"),
    ("win10toast", "win10toast"),
]
HIT_STATUS_DEFAULT = "未处理"
HIT_STATUS_OPTIONS = ["未处理", "已查看", "已联系", "忽略", "收藏"]
MAX_MONITOR_ROWS = 50
MAX_SCAN_PAGES = 50
MAX_PRICE_VALUE = 99999999
MAX_HIT_HISTORY_ITEMS = 500
MAX_STATUS_ITEMS = 1000
MAX_ARCHIVE_ITEMS = 5000
MAX_LOG_LINES = 2000
MAX_LOG_LINE_CHARS = 1200
CORRUPT_JSON_WARNINGS = []
PLATFORM_RISK_COOLDOWN_ROUNDS = {
    "jd": 3,
    "taobao": 1,
}
ITEM_SELECTORS = [
    'a[href*="goofish.com/item?id="]',
    'a[href*="/item?id="]',
    'div[class*="item-card"]',
    'div[class*="SearchList--item"]',
    "li.gl-item",
    "div.gl-i-wrap",
    'a[href*="item.jd.com"]',
    'a[href*="item.taobao.com/item.htm"]',
    'a[href*="detail.tmall.com/item.htm"]',
]
ITEM_READY_SELECTOR = ", ".join(ITEM_SELECTORS)
PAGINATION_INPUT_SELECTOR = 'input[class*="search-pagination-to-page-input"]'
PAGINATION_CONFIRM_SELECTOR = 'button[class*="search-pagination-to-page-confirm-button"]'
DEFAULT_BLACK_WORDS = [
    "求购",
    "不卖",
    "碎屏",
    "借图",
    "引流",
    "慢收",
    "是收",
    "收，看清",
    "拍下不发货",
    "查不了保修",
    "渠道流出",
    "渠道流出来",
    "不零售",
    "批量出售",
    "批发",
    "工厂直销",
    "工厂直发",
    "工厂亲自",
    "厂家直销",
    "清仓",
    "清货",
    "库存",
    "清库存",
    "大甩卖",
    "商用品质",
    "健身房商用",
    "全规格",
    "规格齐全",
    "多种颜色可选",
    "咨询客服",
    "今日特价",
    "直接拍就行",
    "专卖店直供",
    "全新未激活",
    "官方质检",
    "假一赔三",
    "现货数量",
    "欢迎咨询",
    "全国包邮",
    "正品保障",
    "外贸",
    "大厂直出",
    "原单尾单",
    "官旗直发",
    "下定不退",
    "代下",
    "回收",
    "收购",
    "收一台",
    "诚心收",
    "到货即收",
    "可以转给我",
    "配置需求",
]
BUYER_INTENT_PATTERNS = [
    r"(^|[\s，。,.【】#])收一台",
    r"(^|[\s，。,.【】#])收[~～,，、\s]*收[~～,，、\s]*收",
    r"(^|[\s，。,.【】#])求购",
    r"(^|[\s，。,.【】#])回收",
    r"(^|[\s，。,.【】#])收购",
    r"\d[\d\s]{1,8}\s*收",
    r"诚心收",
    r"想收",
    r"慢收",
    r"收机",
    r"计划\s*收一台",
    r"到货即收",
    r"可以转给我",
    r"有(机器|机子|货|设备)的人联系我",
    r"诚心卖的联系",
    r"带价格私聊",
    r"合理就收",
    r"我买(哦|啊|呀|喔)",
    r"我想买",
    r"我要\s*(一台|一个|收|买)",
    r"我只要",
    r"出我一台",
    r"敢.*出我.*敢要",
    r"配置需求",
    r"费用\s*\d+\s*元?\s*代下",
]
BAD_LEARNING_PATTERNS = BUYER_INTENT_PATTERNS + [
    r"看清楚",
    r"拆封也可",
    r"未激活或激活",
    r"淘宝京东的货都可以",
]
GOOD_LEARNING_PHRASES = [
    "自用",
    "闲置",
    "没怎么用",
    "很少用",
    "成色几乎全新",
    "功能正常",
    "无拆修",
    "没磕碰",
    "无磕碰",
    "没划痕",
    "无划痕",
    "配件齐全",
    "箱说齐全",
    "原装电源线",
    "保修",
    "发票",
    "自提",
    "面交",
]
ACCESSORY_LIKE_KEYWORD_TERMS = [
    "充电宝",
    "充电器",
    "数据线",
    "充电线",
    "电源线",
    "电源",
    "保护壳",
    "手机壳",
    "贴膜",
    "钢化膜",
    "支架",
    "底座",
    "扩展坞",
    "键盘",
    "鼠标",
    "显示器",
    "主板",
    "内存",
    "硬盘",
    "固态",
    "ssd",
    "cpu",
    "处理器",
    "镜头",
    "电池",
]
GENERIC_ACCESSORY_TERMS = [
    "保护壳",
    "手机壳",
    "硅胶壳",
    "透明壳",
    "贴膜",
    "钢化膜",
    "支架",
    "底座",
    "挂架",
    "扩展坞",
    "转接头",
    "转换器",
    "数据线",
    "充电线",
    "电源线",
    "遥控器",
    "相机包",
    "镜头盖",
    "屏幕总成",
    "外屏",
    "后盖",
]
GENERIC_SERVICE_TERMS = [
    "维修",
    "租赁",
    "出租",
    "租用",
    "远程",
    "云电脑",
    "云算力",
    "服务器体验",
    "实体macos",
    "macos系统",
    "无押金",
    "1小时起租",
    "定制机",
    "扩容版定制",
    "预装",
    "openclaw",
    "deepseek",
    "装机服务",
    "上门装机",
    "装系统",
    "重装系统",
    "配置咨询",
    "写配置单",
    "不是卖电脑",
    "代拍",
    "代下",
    "教程",
    "图纸",
    "账号",
    "会员",
    "虚拟道具",
    "游戏道具",
    "游戏内",
    "非实体",
    "三角洲行动",
    "手游",
    "端游",
    "代撞",
    "撞车",
    "扫号",
    "上号",
    "包撞车",
    "跟车",
    "包到仓库",
    "不进仓库",
    "不动仓库",
    "追缴",
    "追缴包赔",
]
GENERIC_NON_FUNCTIONAL_TERMS = [
    "模型机",
    "展示机",
    "展示模型",
    "道具机",
    "不能使用",
    "无法使用",
    "不能食用",
    "不具备实际使用功能",
    "不具备任何实际使用功能",
]
PRODUCT_BODY_CONTEXT_TERMS = [
    "主机",
    "本体",
    "整机",
    "裸机",
    "机器",
    "功能正常",
    "正常使用",
    "成色",
    "自用",
    "闲置",
    "购买",
    "买的",
    "京东购入",
    "带原装盒",
    "原装盒",
    "原包装",
    "原配",
    "配件齐全",
    "箱说",
    "无拆修",
    "无拆无修",
    "电池健康",
    "过保",
    "在保",
    "保修",
    "内存",
    "硬盘",
    "固态",
    "外观",
    "磕碰",
    "划痕",
]
KEYWORD_ALIAS_GROUPS = [
    {
        "tokens": ["苹果手机"],
        "aliases": ["苹果手机", "iphone", "苹果iphone"],
    },
    {
        "tokens": ["苹果电脑"],
        "aliases": ["苹果电脑", "macbook", "imac", "macmini", "mac mini", "mac"],
    },
    {
        "tokens": ["苹果笔记本", "苹果笔记本电脑"],
        "aliases": ["苹果笔记本", "苹果笔记本电脑", "macbook"],
    },
]
GENERIC_EMPTY_BOX_TERMS = [
    "空盒",
    "仅盒",
    "盒子单出",
    "包装盒单出",
    "原盒空盒",
    "只有盒",
]


def empty_smart_rules():
    return {
        "blocked_titles": [],
        "blocked_phrases": [],
        "preferred_phrases": [],
        "feedback": [],
    }


def default_rule_options():
    return {
        "filter_accessories": True,
        "filter_empty_boxes": True,
        "filter_services": True,
        "filter_bundles": True,
        "merchant_penalty": True,
    }


def dedupe_text_list(values, limit=200):
    result = []
    seen = set()
    for value in values:
        text = re.sub(r"\s+", " ", str(value)).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def ensure_parent_dir(file_path):
    parent = os.path.dirname(os.path.abspath(file_path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def atomic_write_text(file_path, text):
    ensure_parent_dir(file_path)
    file_path = os.path.abspath(file_path)
    temp_path = f"{file_path}.tmp.{os.getpid()}.{int(time.time() * 1000)}"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, file_path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def atomic_write_json(file_path, data):
    atomic_write_text(file_path, json.dumps(data, ensure_ascii=False, indent=4))


def backup_corrupt_file(file_path, reason):
    if not os.path.exists(file_path):
        return None
    backup_path = (
        f"{file_path}.corrupt-{time.strftime('%Y%m%d_%H%M%S')}.{os.getpid()}.bak"
    )
    try:
        os.replace(file_path, backup_path)
        CORRUPT_JSON_WARNINGS.append(f"{file_path} 已备份为 {backup_path}：{reason}")
        return backup_path
    except Exception as exc:
        CORRUPT_JSON_WARNINGS.append(f"{file_path} 读取异常且备份失败：{reason}；{exc}")
        return None


def load_json_file(file_path, default, expected_type=None):
    if not os.path.exists(file_path):
        return default

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        backup_corrupt_file(file_path, f"JSON 读取失败：{exc}")
        return default

    if expected_type and not isinstance(data, expected_type):
        backup_corrupt_file(file_path, f"JSON 类型错误：期望 {expected_type.__name__}")
        return default

    return data


def take_corrupt_json_warnings():
    warnings = list(CORRUPT_JSON_WARNINGS)
    CORRUPT_JSON_WARNINGS.clear()
    return warnings


def clamp_int(value, default, minimum=None, maximum=None):
    try:
        number = int(value)
    except Exception:
        number = default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def limit_text(value, limit=MAX_LOG_LINE_CHARS):
    text = re.sub(r"\s+", " ", str(value)).strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def redact_sensitive_text(text, title_limit=120):
    text = str(text)

    def redact_url(match):
        raw_url = match.group(0)
        try:
            parsed = urlparse(raw_url)
            sensitive_keys = {
                "token",
                "access_token",
                "refresh_token",
                "cookie",
                "session",
                "sid",
                "user",
                "username",
                "account",
                "phone",
                "mobile",
                "email",
                "password",
            }
            query = []
            for key, value in parse_qsl(parsed.query, keep_blank_values=True):
                if key.lower() in sensitive_keys:
                    query.append((key, "***"))
                else:
                    query.append((key, value))
            return urlunparse(parsed._replace(query=urlencode(query)))
        except Exception:
            return raw_url

    redacted = re.sub(r"https?://[^\s，。；;）)]+", redact_url, text)
    redacted = re.sub(
        r"(?i)(token|cookie|session|sid|account|phone|mobile|password)=([^&\s]+)",
        r"\1=***",
        redacted,
    )
    return limit_text(redacted, title_limit)


def normalize_title_key(title):
    return re.sub(r"\s+", "", title.lower())


def load_smart_rules(file_path=SMART_RULES_FILE):
    rules = empty_smart_rules()
    data = load_json_file(file_path, {}, dict)
    if not data:
        return rules

    for key in ("blocked_titles", "blocked_phrases", "preferred_phrases"):
        rules[key] = dedupe_text_list(data.get(key, []))

    feedback = data.get("feedback", [])
    rules["feedback"] = feedback[-300:] if isinstance(feedback, list) else []
    return rules


def save_smart_rules(rules, file_path=SMART_RULES_FILE):
    cleaned = empty_smart_rules()
    cleaned["blocked_titles"] = dedupe_text_list(rules.get("blocked_titles", []))
    cleaned["blocked_phrases"] = dedupe_text_list(rules.get("blocked_phrases", []))
    cleaned["preferred_phrases"] = dedupe_text_list(rules.get("preferred_phrases", []))
    feedback = rules.get("feedback", [])
    cleaned["feedback"] = feedback[-300:] if isinstance(feedback, list) else []

    atomic_write_json(file_path, cleaned)


def load_item_statuses(file_path=ITEM_STATUS_FILE):
    data = load_json_file(file_path, {}, dict)
    if not data:
        return {}

    statuses = {}
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        status = value.get("status", HIT_STATUS_DEFAULT)
        if status not in HIT_STATUS_OPTIONS:
            status = HIT_STATUS_DEFAULT
        statuses[str(key)] = {
            "status": status,
            "updated_at": str(value.get("updated_at", "")),
            "keyword": str(value.get("keyword", "")),
            "title": str(value.get("title", "")),
            "url": str(value.get("url", "")),
        }
    return statuses


def save_item_statuses(statuses, file_path=ITEM_STATUS_FILE, limit=1000):
    if not isinstance(statuses, dict):
        statuses = {}

    records = []
    for key, value in statuses.items():
        if not isinstance(value, dict):
            continue
        status = value.get("status", HIT_STATUS_DEFAULT)
        if status not in HIT_STATUS_OPTIONS:
            status = HIT_STATUS_DEFAULT
        records.append(
            (
                str(value.get("updated_at", "")),
                str(key),
                {
                    "status": status,
                    "updated_at": str(value.get("updated_at", "")),
                    "keyword": str(value.get("keyword", "")),
                    "title": str(value.get("title", "")),
                    "url": str(value.get("url", "")),
                },
            )
        )

    records.sort(key=lambda item: item[0], reverse=True)
    archived_records = records[limit:]
    if archived_records:
        archive_records(
            f"{file_path}.archive.json",
            [value for _updated_at, _key, value in archived_records],
            limit=5000,
        )
    trimmed = {key: value for _updated_at, key, value in records[:limit]}
    atomic_write_json(file_path, trimmed)


def load_app_settings(file_path=APP_SETTINGS_FILE):
    return load_json_file(file_path, {}, dict)


def save_app_settings(settings, file_path=APP_SETTINGS_FILE):
    if not isinstance(settings, dict):
        settings = {}
    atomic_write_json(file_path, settings)


def load_hit_history(file_path=HIT_HISTORY_FILE):
    return load_json_file(file_path, [], list)[-MAX_ARCHIVE_ITEMS:]


def save_hit_history(items, file_path=HIT_HISTORY_FILE, limit=500):
    if not isinstance(items, list):
        items = []

    cleaned_all = []
    for item in items:
        if not isinstance(item, dict):
            continue
        cleaned_all.append(
            {
                "time": str(item.get("time", "")),
                "status": str(item.get("status", HIT_STATUS_DEFAULT)),
                "platform_name": str(item.get("platform_name", "闲鱼")),
                "keyword": str(item.get("keyword", "")),
                "page_number": item.get("page_number", 1),
                "price": item.get("price", ""),
                "score": item.get("score", ""),
                "level": str(item.get("level", "")),
                "quality_reason": str(item.get("quality_reason", "")),
                "title": str(item.get("title", "")),
                "url": str(item.get("url", "")),
            }
        )

    archived = cleaned_all[:-limit] if limit and len(cleaned_all) > limit else []
    if archived:
        archive_records(f"{file_path}.archive.json", archived, limit=5000)
    cleaned = cleaned_all[-limit:] if limit else cleaned_all
    atomic_write_json(file_path, cleaned)


def archive_records(file_path, records, limit=5000):
    if not records:
        return
    existing = []
    if os.path.exists(file_path):
        data = load_json_file(file_path, [], list)
        existing = [item for item in data if isinstance(item, dict)]
    existing.extend(records)
    if limit:
        existing = existing[-limit:]
    atomic_write_json(file_path, existing)


def append_monitor_log(message, file_path=APP_LOG_FILE, limit_lines=2000):
    line = limit_text(message)
    timestamped = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {line}"
    lines = []
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
        except Exception:
            lines = []
    lines.append(timestamped)
    lines = lines[-limit_lines:]
    atomic_write_text(file_path, "\n".join(lines) + "\n")


def extract_pattern_phrases(title, patterns):
    phrases = []
    for pattern in patterns:
        for match in re.finditer(pattern, title, flags=re.IGNORECASE):
            phrase = re.sub(r"^[\s，。,.【】#]+|[\s，。,.【】#]+$", "", match.group(0))
            phrase = re.sub(r"\s+", " ", phrase).strip()
            if 2 <= len(phrase) <= 30:
                phrases.append(phrase)
    return dedupe_text_list(phrases, limit=12)


def extract_bad_learning_phrases(title):
    phrases = extract_pattern_phrases(title, BAD_LEARNING_PATTERNS)
    if phrases:
        return phrases

    fallback_patterns = [
        r"[^，。,.、\s]{0,8}收[^，。,.、\s]{0,8}",
        r"[^，。,.、\s]{0,8}买[^，。,.、\s]{0,8}",
        r"[^，。,.、\s]{0,8}联系我[^，。,.、\s]{0,8}",
    ]
    return extract_pattern_phrases(title, fallback_patterns)


def extract_good_learning_phrases(title):
    return [
        phrase
        for phrase in GOOD_LEARNING_PHRASES
        if phrase in title
    ]



from .ui import MainWindow

def main():
    print("[DEBUG] 程序入口已执行")
    instance_lock = SingleInstanceLock()
    try:
        if not instance_lock.acquire():
            wake_sent = signal_existing_window()
            if wake_sent:
                return
            app = QApplication.instance()
            if app is None:
                app = QApplication(sys.argv)
            old_count = len(other_monitor_processes())
            extra_tip = f"\n检测到 {old_count} 个历史后台进程，可在主窗口里手动清理。" if old_count else ""
            QMessageBox.information(
                None,
                "软件已在运行",
                "闲鱼监测软件已经在运行，不会重复打开新窗口。"
                "\n未能自动唤回窗口，请从系统托盘图标右键选择“显示窗口”。"
                + extra_tip,
            )
            return

        print("[DEBUG] 正在创建 QApplication")
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        print("[DEBUG] 正在创建主窗口")
        window = MainWindow()
        print("[DEBUG] 正在显示主窗口")
        window.show()
        print("[DEBUG] 即将进入 Qt 事件循环")
        sys.exit(app.exec())
    except Exception:
        error_text = traceback.format_exc()
        print("[ERROR] PyQt 初始化或主窗口启动失败")
        print(error_text)
        with open(STARTUP_LOG_FILE, "w", encoding="utf-8") as f:
            f.write(error_text)

        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        QMessageBox.critical(None, "启动失败", f"软件启动失败，详情见：{STARTUP_LOG_FILE}")

        if sys.stdin and sys.stdin.isatty():
            input("按回车退出...")
    finally:
        instance_lock.release()


