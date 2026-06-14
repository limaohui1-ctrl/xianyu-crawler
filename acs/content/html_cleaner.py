"""
html_cleaner.py — remove boilerplate (nav, footer, ads, sidebars) from HTML.

Strategy:
  1. Parse with BeautifulSoup (lxml).
  2. Strip <script>, <style>, <noscript>, <iframe>, <svg>.
  3. Remove elements matching common boilerplate selectors.
  4. Return cleaned HTML string + removal stats.
"""

import re

from bs4 import BeautifulSoup, NavigableString, Comment, Tag

# Elements to always remove
STRIP_TAGS = {"script", "style", "noscript", "iframe", "svg", "form",
              "input", "select", "textarea", "button", "canvas"}

# Selectors / class-name patterns that indicate boilerplate
BOILERPLATE_PATTERNS = [
    "nav", "footer", "header", "aside", "sidebar",
    "advertisement", "ad-", "ads-", "sponsor", "banner",
    "social", "share", "comment", "related", "recommend",
    "copyright", "breadcrumb", "cookie", "popup", "modal",
    "menu", "pagination", "tag-cloud", "widget",
]


def _element_matches_boilerplate(el: Tag) -> bool:
    """Check if a tag looks like boilerplate by tag name, id, or class."""
    tag_name = (el.name or "").lower()
    el_id = " ".join(el.get("id", []) if isinstance(el.get("id"), list) else [el.get("id", "") or ""]).lower()
    classes = " ".join(el.get("class", []) if isinstance(el.get("class"), list) else []).lower()
    role = (el.get("role", "") or "").lower()

    combined = f"{tag_name} {el_id} {classes} {role}"
    for pattern in BOILERPLATE_PATTERNS:
        if pattern in combined:
            return True
    return False


def clean_html(html: str) -> dict:
    """
    Clean HTML by removing boilerplate.

    Args:
        html: Raw HTML string.

    Returns:
        dict with:
          - cleaned_html: cleaned HTML string (or empty on failure)
          - removed_count: number of elements removed
          - cleaned_text_len: length of extracted text after cleaning
          - error: error message if any
    """
    result = {
        "cleaned_html": "",
        "removed_count": 0,
        "cleaned_text_len": 0,
        "error": "",
    }

    if not html or not html.strip():
        result["error"] = "Empty HTML input"
        return result

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as e:
        result["error"] = f"HTML parse failed: {e}"
        return result

    removed = 0

    # 1. Strip noise tags
    for tag in soup.find_all(STRIP_TAGS):
        tag.decompose()
        removed += 1

    # 2. Remove comments
    for comment in soup.find_all(text=lambda t: isinstance(t, Comment)):
        comment.extract()
        removed += 1

    # 3. Remove boilerplate by heuristics
    for el in list(soup.descendants):
        if not isinstance(el, Tag):
            continue
        if el.attrs is None:
            continue
        if _element_matches_boilerplate(el):
            el.decompose()
            removed += 1

    result["removed_count"] = removed
    result["cleaned_html"] = str(soup)
    result["cleaned_text_len"] = len(soup.get_text(separator="\n", strip=True))
    return result
