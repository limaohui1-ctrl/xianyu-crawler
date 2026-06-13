import base64
import json
import mimetypes
import os
import re
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from universal_core import (
    load_ai_settings,
    AI_PROVIDER_PRESETS,
    AI_MODEL_USE_CASE_PRESETS,
    AI_SNAPSHOT_TEXT_LIMIT,
    extract_json_from_text,
    page_snapshot_from_html,
    record_recoverable_error,
    mask_api_key,
    compact_text,
    clean_text,
    normalize_url,
)

from core_firecrawl import FirecrawlClient, FirecrawlConfig


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


def ai_extract_file_to_table(file_path, instruction="", settings=None, firecrawl_config=None):
    firecrawl = FirecrawlConfig.from_dict(firecrawl_config)
    if firecrawl.enabled and firecrawl.use_parse and firecrawl.is_usable():
        try:
            return FirecrawlClient(firecrawl).parse_file_to_table(file_path, instruction=instruction)
        except Exception as exc:
            record_recoverable_error(
                "Firecrawl Parse 文件解析失败，已改用本地/AI 文件提取",
                exc,
                details={"file_path": file_path},
            )
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
