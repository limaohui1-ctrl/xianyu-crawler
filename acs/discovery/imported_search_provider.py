"""Imported Search Provider — parse user-imported files into CandidateUrl list.

Supports: CSV, JSON, TXT (one URL per line), Markdown tables.
Never calls external APIs. Never leaks keys.
"""
import csv
import json
import os
import re
from typing import List, Optional
from .candidate_url import CandidateUrl
from .discovery_config import get_config


class ImportedSearchProvider:
    """Parse user-imported files into CandidateUrl objects.

    Supported formats:
      - .txt / .urls: One URL per line
      - .csv: Columns must include 'url' (required), 'title'/'description'/'snippet' optional
      - .json: Array of objects with 'url' field (at minimum)
      - .md: Extract URLs from markdown link syntax or plain URLs
    """

    def __init__(self):
        self.config = get_config()

    def load(self, file_path: str, topic: str = "",
             keywords: Optional[List[str]] = None) -> List[CandidateUrl]:
        """Parse a file and return CandidateUrl list.

        Args:
            file_path: Path to .txt, .csv, .json, or .md file
            topic: Topic for relevance context
            keywords: Keywords for matching

        Returns:
            List of CandidateUrl objects
        """
        ext = os.path.splitext(file_path)[1].lower()
        raw_urls = []

        if ext == ".csv":
            raw_urls = self._parse_csv(file_path)
        elif ext == ".json":
            raw_urls = self._parse_json(file_path)
        elif ext in (".md", ".markdown"):
            raw_urls = self._parse_markdown(file_path)
        else:
            # .txt, .urls, or any other text format
            raw_urls = self._parse_txt(file_path)

        return self._to_candidates(raw_urls, topic, keywords or [])

    def _parse_txt(self, path: str) -> list:
        results = []
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Extract URL from line (may contain comment after URL)
                match = re.search(r'(https?://\S+)', line)
                if match:
                    results.append({"url": match.group(1), "title": "", "snippet": line})
                elif not line.startswith(("http://", "https://")):
                    continue
                else:
                    results.append({"url": line, "title": "", "snippet": ""})
        return results[:self.config.import_max_rows]

    def _parse_csv(self, path: str) -> list:
        results = []
        with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return results
            for row in reader:
                url = (row.get("url") or row.get("URL") or row.get("link") or "").strip()
                if not url or not url.startswith(("http://", "https://")):
                    continue
                results.append({
                    "url": url,
                    "title": (row.get("title") or row.get("name") or "").strip(),
                    "snippet": (row.get("description") or row.get("snippet") or
                                row.get("summary") or "").strip(),
                })
        return results[:self.config.import_max_rows]

    def _parse_json(self, path: str) -> list:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            # Try common wrappers: 'results', 'items', 'data'
            items = (data.get("results") or data.get("items") or data.get("data") or [data])
        else:
            return []
        results = []
        for item in items:
            url = (item.get("url") or item.get("URL") or item.get("link") or "").strip()
            if not url or not url.startswith(("http://", "https://")):
                continue
            results.append({
                "url": url,
                "title": (item.get("title") or item.get("name") or "").strip(),
                "snippet": (item.get("description") or item.get("snippet") or
                            item.get("summary") or "").strip(),
            })
        return results[:self.config.import_max_rows]

    def _parse_markdown(self, path: str) -> list:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        results = []
        # [text](url) links
        for match in re.finditer(r'\[([^\]]*)\]\((https?://[^\)]+)\)', text):
            results.append({"url": match.group(2), "title": match.group(1), "snippet": ""})
        # Plain URLs
        for match in re.finditer(r'(?<!\()(https?://\S+)', text):
            url = match.group(1)
            if not any(r["url"] == url for r in results):
                results.append({"url": url, "title": "", "snippet": ""})
        return results[:self.config.import_max_rows]

    def _to_candidates(self, raw: list, topic: str,
                       keywords: List[str]) -> List[CandidateUrl]:
        from urllib.parse import urlparse
        candidates = []
        for item in raw:
            url = item["url"]
            domain = urlparse(url).netloc.replace("www.", "")
            candidates.append(CandidateUrl(
                url=url,
                title=item.get("title", ""),
                snippet=item.get("snippet", ""),
                source_domain=domain,
                source_type="webpage",
                discovery_method="import-file",
                matched_keywords=keywords or [],
            ))
        return candidates
