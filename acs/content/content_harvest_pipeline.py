"""
content_harvest_pipeline.py — end-to-end harvest pipeline.

Flow:
  1. Load selected_urls.txt
  2. For each URL: fetch → extract_article
  3. Quality score each article
  4. Deduplicate
  5. Export results (JSON/CSV/Markdown/Excel)
"""

import json
import os
import time
from typing import List, Optional
from urllib.parse import urlparse

from .article_extractor import extract_article
from .content_quality_scorer import score_quality
from .content_deduplicator import deduplicate, filter_duplicates


DEFAULT_HARVEST_DIR = "acs_data/harvest"


def run_harvest(urls: List[str],
                keywords: Optional[List[str]] = None,
                include_duplicates: bool = True,
                timeout: int = 30) -> List[dict]:
    """
    Run the full content harvest pipeline on a list of URLs.

    Args:
        urls: List of URLs to process.
        keywords: Keywords for quality scoring.
        include_duplicates: Include duplicate results in output.
        timeout: HTTP timeout per URL.

    Returns:
        List of enriched ContentRecord dicts with quality and dedup fields.
    """
    if not urls:
        return []

    articles = []

    for i, url in enumerate(urls):
        if not url or not url.strip():
            continue

        # ── Fetch ──
        html = ""
        content_type = ""
        http_status = 200
        try:
            from urllib.request import Request, urlopen
            from urllib.error import HTTPError, URLError

            req = Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/125.0 Safari/537.36"
            })
            resp = urlopen(req, timeout=timeout)
            html = resp.read().decode("utf-8", errors="replace")
            content_type = resp.headers.get("Content-Type", "")
            http_status = resp.status
        except HTTPError as e:
            http_status = e.code
            html = e.read().decode("utf-8", errors="replace") if e.fp else ""
        except Exception as e:
            http_status = -1
            articles.append({
                "url": url,
                "title": "",
                "main_text": "",
                "summary": "",
                "author": "",
                "publish_time": "",
                "source_domain": urlparse(url).netloc,
                "doc_type": "unknown",
                "text_length": 0,
                "paragraph_count": 0,
                "status": "失败",
                "error": f"Fetch failed: {e}",
                "quality_label": "low",
            })
            continue

        # ── Extract ──
        article = extract_article(
            html=html,
            url=url,
            content_type_header=content_type,
            http_status=http_status,
        )
        articles.append(article)

    # ── Quality score ──
    for article in articles:
        quality = score_quality(article, keywords)
        article["quality_score"] = quality["score"]
        article["quality_status"] = quality["status_label"]
        article["quality_flags"] = quality.get("flags", [])
        article["quality_reasons"] = quality.get("reasons", [])
        article["keyword_hits"] = _count_keyword_hits(article.get("main_text", ""), keywords)

    # ── Dedup ──
    articles = deduplicate(articles)

    # ── Summary stats ──
    stats = {
        "total": len(articles),
        "success": sum(1 for a in articles if a.get("status") == "成功"),
        "failed": sum(1 for a in articles if a.get("status") == "失败"),
        "pdf": sum(1 for a in articles if a.get("doc_type") == "pdf"),
        "high_quality": sum(1 for a in articles if a.get("quality_status") == "高质量"),
        "usable": sum(1 for a in articles if a.get("quality_status") == "可用"),
        "needs_review": sum(1 for a in articles if a.get("quality_status") == "需复核"),
        "duplicates": sum(1 for a in articles if a.get("is_duplicate")),
    }

    # Attach stats to first article or return separately
    if articles:
        articles[0]["_harvest_stats"] = stats

    return articles


def _count_keyword_hits(text: str, keywords: Optional[List[str]]) -> int:
    """Count how many keywords appear in the text."""
    if not keywords or not text:
        return 0
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw.lower() in text_lower)


def save_harvest_results(articles: List[dict],
                         output_dir: str = DEFAULT_HARVEST_DIR) -> dict:
    """Save harvest results to JSON. Returns paths dict."""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    paths = {}

    # JSON
    json_path = os.path.join(output_dir, f"harvest_{timestamp}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    paths["json"] = json_path

    # CSV
    csv_path = os.path.join(output_dir, f"harvest_{timestamp}.csv")
    _save_csv(articles, csv_path)
    paths["csv"] = csv_path

    # Markdown
    md_path = os.path.join(output_dir, f"harvest_{timestamp}.md")
    _save_markdown(articles, md_path)
    paths["markdown"] = md_path

    return paths


def _save_csv(articles: List[dict], path: str):
    """Save articles to CSV."""
    import csv
    fields = ["url", "title", "source_domain", "doc_type", "summary",
              "quality_score", "quality_status", "status", "error",
              "keyword_hits", "is_duplicate", "duplicate_reason",
              "publish_time", "author", "text_length"]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for a in articles:
            row = {k: a.get(k, "") for k in fields}
            row["is_duplicate"] = "是" if row["is_duplicate"] else ""
            writer.writerow(row)


def _save_markdown(articles: List[dict], path: str):
    """Save articles to Markdown."""
    lines = []
    lines.append("# ACS 资料采集结果\n")
    stats = articles[0].get("_harvest_stats", {}) if articles else {}
    if stats:
        lines.append(f"- 总数: {stats.get('total', 0)}")
        lines.append(f"- 成功: {stats.get('success', 0)}")
        lines.append(f"- 失败: {stats.get('failed', 0)}")
        lines.append(f"- PDF: {stats.get('pdf', 0)}")
        lines.append(f"- 高质量: {stats.get('high_quality', 0)}")
        lines.append(f"- 重复: {stats.get('duplicates', 0)}")
        lines.append("")

    for i, a in enumerate(articles, 1):
        dup_tag = " **[重复]**" if a.get("is_duplicate") else ""
        lines.append(f"## {i}. {a.get('title', '(无标题)')}{dup_tag}")
        lines.append(f"")
        lines.append(f"- **URL**: {a.get('url', '')}")
        lines.append(f"- **来源**: {a.get('source_domain', '')}")
        lines.append(f"- **类型**: {a.get('doc_type', '')}")
        lines.append(f"- **质量**: {a.get('quality_status', '')} ({a.get('quality_score', 0)}分)")
        lines.append(f"- **状态**: {a.get('status', '')}")
        if a.get("error"):
            lines.append(f"- **错误**: {a.get('error', '')}")
        if a.get("is_duplicate"):
            lines.append(f"- **重复原因**: {a.get('duplicate_reason', '')}")
        lines.append(f"")
        summary = a.get("summary", "") or a.get("main_text", "")[:200]
        if summary:
            lines.append(f"> {summary}")
            lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def harvest_to_csv_string(articles: List[dict]) -> str:
    """Return articles as CSV string."""
    import io, csv
    out = io.StringIO()
    fields = ["url", "title", "source_domain", "doc_type", "summary",
              "quality_score", "quality_status", "status", "error",
              "keyword_hits", "is_duplicate", "duplicate_reason",
              "publish_time", "author", "text_length"]
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for a in articles:
        row = {k: a.get(k, "") for k in fields}
        row["is_duplicate"] = "是" if row["is_duplicate"] else ""
        writer.writerow(row)
    return out.getvalue()


def harvest_to_markdown_string(articles: List[dict]) -> str:
    """Return articles as Markdown string."""
    lines = []
    lines.append("# ACS 资料采集结果\n")
    stats = articles[0].get("_harvest_stats", {}) if articles else {}
    if stats:
        lines.append(f"- 总数: {stats.get('total', 0)}")
        lines.append(f"- 成功: {stats.get('success', 0)}")
        lines.append(f"- 失败: {stats.get('failed', 0)}")
        lines.append(f"- PDF: {stats.get('pdf', 0)}")
        lines.append(f"- 高质量: {stats.get('high_quality', 0)}")
        lines.append(f"- 重复: {stats.get('duplicates', 0)}")
        lines.append("")

    for i, a in enumerate(articles, 1):
        dup_tag = " **[重复]**" if a.get("is_duplicate") else ""
        lines.append(f"## {i}. {a.get('title', '(无标题)')}{dup_tag}")
        lines.append(f"")
        lines.append(f"- **URL**: {a.get('url', '')}")
        lines.append(f"- **来源**: {a.get('source_domain', '')}")
        lines.append(f"- **类型**: {a.get('doc_type', '')}")
        lines.append(f"- **质量**: {a.get('quality_status', '')} ({a.get('quality_score', 0)}分)")
        lines.append(f"- **状态**: {a.get('status', '')}")
        if a.get("error"):
            lines.append(f"- **错误**: {a.get('error', '')}")
        if a.get("is_duplicate"):
            lines.append(f"- **重复原因**: {a.get('duplicate_reason', '')}")
        lines.append(f"")
        summary = a.get("summary", "") or a.get("main_text", "")[:200]
        if summary:
            lines.append(f"> {summary}")
            lines.append("")

    return "\n".join(lines)
