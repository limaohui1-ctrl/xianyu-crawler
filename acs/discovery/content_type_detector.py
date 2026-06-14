"""ContentTypeDetector — identify content category (topic level) from URL and snippet.

NOTE: This classifies content by SUBJECT CATEGORY (news/policy/article/data/case),
NOT by file format. For file format detection (webpage/pdf/doc/xls/csv), use
acs.content.document_type_detector instead.
"""
import re
from typing import List


# Known extension → content type mapping
EXTENSION_MAP = {
    ".pdf": "pdf",
    ".doc": "doc", ".docx": "doc",
    ".xls": "xls", ".xlsx": "xls",
    ".csv": "csv",
    ".ppt": "ppt", ".pptx": "ppt",
    ".html": "webpage", ".htm": "webpage",
}

# Domain patterns that suggest specific content types
DOMAIN_TYPE_HINTS = {
    "news": r"news\.|xinwen|信息|新闻|medi",
    "policy": r"gov\.cn|\.gov\.|zhengce|policy|法律法规|政策|法规|条例|公告|通知|公示",
    "article": r"blog|article|学术|journal|research|paper|论文|研究",
    "data": r"data|统计|opendata|tongji",
}

# Snippet language hints for content type
SNIPPET_HINTS = [
    (r"新闻|发布|报道", "news"),
    (r"政策|法规|条例|公告|通知|规定|办法", "policy"),
    (r"论文|研究|学术|摘要|abstract", "article"),
    (r"统计数据|指标|年度|报表", "data"),
    (r"案例|实例|做法|经验", "case"),
]


def detect_content_type(url: str, title: str = "", snippet: str = "") -> str:
    """Detect the content type of a candidate URL.

    Priority: URL extension > domain patterns > snippet hints

    Returns one of: webpage, pdf, doc, xls, csv, ppt,
                   news, policy, article, data, case, unknown
    """
    if not url:
        return "unknown"

    # 1. URL extension (most reliable)
    url_lower = url.lower()
    for ext, ctype in EXTENSION_MAP.items():
        if url_lower.endswith(ext) or f"{ext}?" in url_lower:
            return ctype

    # 2. Domain patterns
    combined = f"{url_lower} {title} {snippet}"
    for ctype, pattern in DOMAIN_TYPE_HINTS.items():
        if re.search(pattern, combined):
            return ctype

    # 3. Snippet hints
    for pattern, ctype in SNIPPET_HINTS:
        if re.search(pattern, snippet or "") or re.search(pattern, title or ""):
            return ctype

    return "webpage"


def classify_candidates(candidates: List[dict]) -> List[dict]:
    """Add content_type field to each candidate."""
    for c in candidates:
        c["content_type"] = detect_content_type(
            c.get("url", ""), c.get("title", ""), c.get("snippet", "")
        )
    return candidates
