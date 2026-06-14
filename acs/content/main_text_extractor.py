"""
main_text_extractor.py — extract the main body text from cleaned HTML.

Strategy:
  1. Use BeautifulSoup to walk the DOM tree.
  2. Score paragraphs by text density, position, and typical content markers.
  3. Collect top-scored text blocks as the main content.
  4. Return: title, main_text, summary, paragraphs.
"""

from bs4 import BeautifulSoup, Tag
from typing import List


def extract_main_text(cleaned_html: str, min_paragraph_len: int = 25) -> dict:
    """
    Extract main text from cleaned HTML.

    Args:
        cleaned_html: HTML already passed through html_cleaner.
        min_paragraph_len: Minimum length for a paragraph to be included.

    Returns:
        dict:
          - main_text: full concatenated body text
          - summary: first 200 chars of main_text
          - paragraphs: list of individual paragraph strings
          - paragraph_count: number of extracted paragraphs
          - text_length: total character count
          - error: error message if extraction failed
    """
    result = {
        "main_text": "",
        "summary": "",
        "paragraphs": [],
        "paragraph_count": 0,
        "text_length": 0,
        "error": "",
    }

    if not cleaned_html or not cleaned_html.strip():
        result["error"] = "Empty HTML — no text to extract"
        return result

    try:
        soup = BeautifulSoup(cleaned_html, "lxml")
    except Exception as e:
        result["error"] = f"HTML parse failed: {e}"
        return result

    # Collect text from block-level elements
    block_tags = {"p", "div", "article", "section", "main", "blockquote",
                  "li", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6", "pre"}

    paragraphs = []
    for tag in soup.find_all(block_tags):
        text = tag.get_text(separator=" ", strip=True)
        # Skip boilerplate-y small text
        if len(text) < min_paragraph_len:
            continue
        # Skip elements that are mostly links (nav menus)
        links = tag.find_all("a")
        link_text = " ".join(a.get_text(strip=True) for a in links)
        if len(link_text) > len(text) * 0.7:
            continue
        paragraphs.append(text)

    # Fallback: if no structured paragraphs, use whole body text split by newlines
    if not paragraphs:
        full_text = soup.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in full_text.split("\n") if len(line.strip()) >= min_paragraph_len]
        paragraphs = lines

    main_text = "\n\n".join(paragraphs)
    summary = main_text[:200] + ("..." if len(main_text) > 200 else "")

    result["main_text"] = main_text
    result["summary"] = summary
    result["paragraphs"] = paragraphs
    result["paragraph_count"] = len(paragraphs)
    result["text_length"] = len(main_text)

    if not main_text.strip():
        result["error"] = "No meaningful text extracted from page"
    return result
