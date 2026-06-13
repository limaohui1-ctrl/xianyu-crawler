"""Logging and crawl-discovery UI helpers."""

from ui_registry import register
from universal_core import compact_text

@register("append_log")
def append_log(self, message, level="INFO"):
    prefix = ""
    if level == "WARN":
        prefix = "[WARN] "
    elif level == "ERROR":
        prefix = "[ERROR] "
    self.record_crawl_discovery_message(message)
    if hasattr(self, "log_output"):
        self.log_output.append(f"{prefix}{message}")
    if hasattr(self, "simple_status_label"):
        self.simple_status_label.setText(str(message))
    if hasattr(self, "ai_output"):
        self.ai_output.appendPlainText(f"{prefix}{str(message)}")

@register("log_info")
def log_info(self, message):
    self.append_log(message, "INFO")

@register("log_warn")
def log_warn(self, message):
    self.append_log(message, "WARN")

@register("log_error")
def log_error(self, message):
    self.append_log(message, "ERROR")

@register("record_crawl_discovery_message")
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

@register("append_ai_output")
def append_ai_output(self, message):
    self.ai_output.appendPlainText(str(message))
