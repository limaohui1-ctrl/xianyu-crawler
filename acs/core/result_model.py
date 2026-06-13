"""
Unified result schema — the canonical output format for all parsed pages.

Every parser (CSS, XPath, JSON, JSONLD, fallback) emits results conforming to
this schema.  All fields are optional except `url` and `parsed_at`.

This replaces the ad-hoc dicts currently returned by UniversalExtractor.extract().
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import hashlib
import json
import time


# ── Field-level metadata for export headers ─────────────────────

FIELD_META = {
    "parsed_at":       ("采集时间",   "Record creation timestamp"),
    "url":             ("网址",       "Source URL"),
    "domain":          ("域名",       "Domain extracted from URL"),
    "template_name":   ("模板",       "Template used for parsing"),
    "title":           ("标题",       "Page title"),
    "price":           ("价格",       "Price field (product / listing)"),
    "published_time":  ("时间",       "Publication / update time"),
    "author":          ("作者",       "Author / seller / company"),
    "body":            ("正文",       "Main body text"),
    "images":          ("图片",       "Extracted image URLs"),
    "links":           ("链接",       "Extracted hyperlinks"),
    "tables":          ("表格",       "Page tables (textified)"),
    "structured_data": ("结构化数据",  "JSON-LD / microdata extracted"),
    "parser_used":     ("解析器",      "Which parser produced this record"),
    "fetch_quality":   ("采集质量",    "How the page was fetched"),
    "content_hash":    ("内容哈希",    "Content-based dedup hash"),
    "completeness":    ("完整度",      "Completeness score 0–100"),
    "quality_label":   ("质量标签",    "Quality label (high/medium/low)"),
    "missing_fields":  ("缺失字段",    "Fields that are empty"),
    "error":           ("错误",       "Error message (if any)"),
    "error_category":  ("错误类别",    "Error classification"),
    "warnings":        ("警告",       "Non-fatal warnings"),
}

FIELD_ORDER = list(FIELD_META.keys())


def _make_content_hash(record: dict) -> str:
    """Deterministic content hash for dedup — independent of metadata."""
    parts = [
        record.get("title", ""),
        record.get("body", ""),
        record.get("price", ""),
        record.get("author", ""),
        record.get("published_time", ""),
    ]
    cannibal = "|".join(p.strip()[:2000] for p in parts)
    return hashlib.sha256(cannibal.encode("utf-8", errors="ignore")).hexdigest()[:16]


@dataclass
class ParseWarning:
    """A non-fatal warning during parsing."""
    code: str = ""          # e.g. "IMAGE_TRUNCATED", "TABLE_PARSE_FAILED"
    message: str = ""
    field: str = ""         # which field was affected

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "field": self.field}


@dataclass
class PageImage:
    """A single extracted image with optional metadata."""
    src: str = ""
    alt: str = ""
    width: Optional[int] = None
    height: Optional[int] = None

    def to_dict(self) -> dict:
        result: dict = {"src": self.src}
        if self.alt:
            result["alt"] = self.alt
        if self.width:
            result["width"] = self.width
        if self.height:
            result["height"] = self.height
        return result


@dataclass
class PageLink:
    """A single extracted hyperlink."""
    url: str = ""
    text: str = ""
    is_internal: bool = False

    def to_dict(self) -> dict:
        return {"url": self.url, "text": self.text, "is_internal": self.is_internal}


@dataclass
class PageTable:
    """A single extracted table, stored as list-of-lists."""
    headers: List[str] = field(default_factory=list)
    rows: List[List[str]] = field(default_factory=list)
    caption: str = ""

    def to_dict(self) -> dict:
        result: dict = {"headers": self.headers, "rows": self.rows}
        if self.caption:
            result["caption"] = self.caption
        return result

    def to_text(self) -> str:
        """Flatten to human-readable text for the 'tables' field."""
        lines = []
        if self.caption:
            lines.append(f"[{self.caption}]")
        if self.headers:
            lines.append("\t".join(self.headers))
        for row in self.rows:
            lines.append("\t".join(str(c) for c in row))
        return "\n".join(lines)


@dataclass
class ParseResult:
    """The unified output of parsing one page."""

    # ── required fields ──
    url: str = ""
    parsed_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))

    # ── identification ──
    domain: str = ""
    template_name: str = "auto"

    # ── extracted content ──
    title: str = ""
    price: str = ""
    published_time: str = ""
    author: str = ""
    body: str = ""
    images: List[str] = field(default_factory=list)        # URLs as plain strings
    links: List[str] = field(default_factory=list)         # URLs as plain strings
    tables: List[str] = field(default_factory=list)        # Textified tables

    # ── rich data ──
    structured_data: List[dict] = field(default_factory=list)  # JSON-LD items
    page_images: List[PageImage] = field(default_factory=list)
    page_links: List[PageLink] = field(default_factory=list)
    page_tables: List[PageTable] = field(default_factory=list)

    # ── metadata ──
    parser_used: str = ""              # e.g. "css", "xpath", "jsonld"
    fetch_quality: str = "full"        # full | degraded_static | failed
    content_hash: str = ""             # computed on build
    completeness: int = 0              # 0–100
    quality_label: str = "low"         # high | medium | low
    missing_fields: List[str] = field(default_factory=list)
    error: str = ""
    error_category: str = ""
    warnings: List[ParseWarning] = field(default_factory=list)

    # ── raw data (for debugging / reprocessing) ──
    raw_html: str = ""                 # optional — may be large
    raw_json: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ── build / finalize ──

    def build(self):
        """Compute derived fields: domain, content_hash, completeness."""
        from urllib.parse import urlparse
        try:
            self.domain = urlparse(self.url).netloc.lower()
        except Exception:
            self.domain = ""

        self.content_hash = _make_content_hash(self.to_record_dict())

        # Count non-empty content fields
        content_fields = {
            "title": self.title,
            "body": self.body,
            "price": self.price,
            "author": self.author,
            "published_time": self.published_time,
            "images": bool(self.images),
            "links": bool(self.links),
            "tables": bool(self.tables),
            "structured_data": bool(self.structured_data),
        }
        filled = sum(1 for v in content_fields.values() if v)
        total = len(content_fields)
        self.completeness = int(round(filled / total * 100)) if total else 0

        # Set quality label
        if self.completeness >= 70:
            self.quality_label = "high"
        elif self.completeness >= 35:
            self.quality_label = "medium"
        else:
            self.quality_label = "low"

        # Missing fields
        self.missing_fields = [k for k, v in content_fields.items() if not v]

    # ── serialization ──

    def to_dict(self) -> dict:
        """Full dict including rich types for programmatic use."""
        return {
            "parsed_at": self.parsed_at,
            "url": self.url,
            "domain": self.domain,
            "template_name": self.template_name,
            "title": self.title,
            "price": self.price,
            "published_time": self.published_time,
            "author": self.author,
            "body": self.body,
            "images": self.images,
            "links": self.links,
            "tables": self.tables,
            "structured_data": self.structured_data,
            "parser_used": self.parser_used,
            "fetch_quality": self.fetch_quality,
            "content_hash": self.content_hash,
            "completeness": self.completeness,
            "quality_label": self.quality_label,
            "missing_fields": self.missing_fields,
            "error": self.error,
            "error_category": self.error_category,
            "page_images": [i.to_dict() for i in self.page_images],
            "page_links": [l.to_dict() for l in self.page_links],
            "page_tables": [t.to_dict() for t in self.page_tables],
            "warnings": [w.to_dict() for w in self.warnings],
            "metadata": dict(self.metadata),
        }

    def to_record_dict(self) -> dict:
        """Flat dict suitable for CSV/TSV export — matches existing FIELD_HEADERS.

        Images, links, tables are '\n'-joined strings.
        """
        images_text = "\n".join(self.images)
        links_text = "\n".join(self.links)
        tables_text = "\n\n".join(self.tables)

        # Append structured data as text
        sd_texts = []
        for item in self.structured_data:
            sd_texts.append(json.dumps(item, ensure_ascii=False))
        if sd_texts:
            tables_text = (tables_text + "\n\n--- 结构化数据 ---\n" +
                          "\n".join(sd_texts)).strip()

        return {
            "采集时间":    self.parsed_at,
            "网址":        self.url,
            "域名":        self.domain,
            "模板":        self.template_name,
            "标题":        self.title,
            "价格":        self.price,
            "时间":        self.published_time,
            "作者":        self.author,
            "正文":        self.body,
            "图片":        images_text,
            "链接":        links_text,
            "表格":        tables_text,
            "完整度":      str(self.completeness),
            "缺少资料":    "、".join(self.missing_fields),
            "内容指纹":    self.content_hash,
            "是否变化":    "",
            "错误":        self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ParseResult":
        return cls(
            url=str(data.get("url", "")),
            parsed_at=str(data.get("parsed_at", "")),
            domain=str(data.get("domain", "")),
            template_name=str(data.get("template_name", "auto")),
            title=str(data.get("title", "")),
            price=str(data.get("price", "")),
            published_time=str(data.get("published_time", "")),
            author=str(data.get("author", "")),
            body=str(data.get("body", "")),
            images=list(data.get("images", [])),
            links=list(data.get("links", [])),
            tables=list(data.get("tables", [])),
            structured_data=list(data.get("structured_data", [])),
            parser_used=str(data.get("parser_used", "")),
            fetch_quality=str(data.get("fetch_quality", "full")),
            content_hash=str(data.get("content_hash", "")),
            completeness=int(data.get("completeness", 0)),
            quality_label=str(data.get("quality_label", "low")),
            missing_fields=list(data.get("missing_fields", [])),
            error=str(data.get("error", "")),
            error_category=str(data.get("error_category", "")),
            metadata=dict(data.get("metadata", {})),
        )
