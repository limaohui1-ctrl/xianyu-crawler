"""Firecrawl-compatible remote scraping adapter for the desktop collector."""

import json
import mimetypes
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from html import unescape
from typing import Callable, Optional
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from core_export import clean_text, now_text
from core_urls import normalize_url, url_domain


def safe_int(value, default=0, minimum=None, maximum=None):
    try:
        if isinstance(value, bool):
            number = int(value)
        elif isinstance(value, (int, float)):
            number = int(value)
        else:
            text = str(value).strip()
            number = int(float(text)) if text else int(default)
    except Exception:
        number = int(default)
    if minimum is not None:
        number = max(int(minimum), number)
    if maximum is not None:
        number = min(int(maximum), number)
    return number


def safe_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "启用", "是"}:
        return True
    if text in {"0", "false", "no", "off", "停用", "否"}:
        return False
    return bool(default)


def safe_list(value, default=None):
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return list(default or [])


FIRECRAWL_DEFAULT_BASE_URL = "https://api.firecrawl.dev"
FIRECRAWL_DEFAULT_FORMATS = ["markdown", "html", "links"]
FIRECRAWL_MAX_PARSE_FILE_BYTES = 50 * 1024 * 1024


@dataclass
class FirecrawlConfig:
    enabled: bool = False
    api_key: str = ""
    base_url: str = FIRECRAWL_DEFAULT_BASE_URL
    formats: list[str] = field(default_factory=lambda: list(FIRECRAWL_DEFAULT_FORMATS))
    only_main_content: bool = True
    use_map: bool = True
    map_limit: int = 10
    use_search: bool = False
    search_query: str = ""
    search_limit: int = 5
    search_sources: list[str] = field(default_factory=lambda: ["web"])
    use_extract: bool = False
    extract_prompt: str = ""
    extract_schema: dict = field(default_factory=dict)
    extract_enable_web_search: bool = False
    extract_poll_interval: int = 2
    extract_timeout_seconds: int = 60
    use_batch: bool = False
    batch_max_concurrency: int = 5
    batch_poll_interval: int = 2
    batch_timeout_seconds: int = 120
    use_crawl: bool = False
    crawl_limit: int = 10
    crawl_max_depth: int = 2
    crawl_allow_external_links: bool = False
    crawl_poll_interval: int = 2
    crawl_timeout_seconds: int = 180
    use_parse: bool = False
    use_interact: bool = False
    interact_prompt: str = ""
    interact_code: str = ""
    interact_language: str = "node"
    interact_timeout_seconds: int = 60
    interact_wait_ms: int = 0
    timeout_seconds: int = 45
    max_retries: int = 2

    @classmethod
    def from_dict(cls, source=None):
        source = dict(source or {})
        api_key = str(source.get("api_key") or os.environ.get("FIRECRAWL_API_KEY") or "").strip()
        formats = safe_list(source.get("formats") or FIRECRAWL_DEFAULT_FORMATS)
        formats = [str(item).strip() for item in formats if str(item).strip()]
        search_sources = safe_list(source.get("search_sources") or ["web"])
        search_sources = [str(item).strip() for item in search_sources if str(item).strip()]
        extract_schema = source.get("extract_schema") or {}
        if isinstance(extract_schema, str):
            try:
                extract_schema = json.loads(extract_schema)
            except Exception:
                extract_schema = {}
        base_url = str(source.get("base_url") or FIRECRAWL_DEFAULT_BASE_URL).strip() or FIRECRAWL_DEFAULT_BASE_URL
        return cls(
            enabled=safe_bool(source.get("enabled", False), False),
            api_key=api_key,
            base_url=base_url.rstrip("/"),
            formats=formats or list(FIRECRAWL_DEFAULT_FORMATS),
            only_main_content=safe_bool(source.get("only_main_content", True), True),
            use_map=safe_bool(source.get("use_map", True), True),
            map_limit=safe_int(source.get("map_limit"), 10, 1, 1000),
            use_search=safe_bool(source.get("use_search", False), False),
            search_query=clean_text(source.get("search_query") or "", 500),
            search_limit=safe_int(source.get("search_limit"), 5, 1, 100),
            search_sources=search_sources or ["web"],
            use_extract=safe_bool(source.get("use_extract", False), False),
            extract_prompt=clean_text(source.get("extract_prompt") or "", 2000),
            extract_schema=extract_schema if isinstance(extract_schema, dict) else {},
            extract_enable_web_search=safe_bool(source.get("extract_enable_web_search", False), False),
            extract_poll_interval=safe_int(source.get("extract_poll_interval"), 2, 1, 30),
            extract_timeout_seconds=safe_int(source.get("extract_timeout_seconds"), 60, 5, 600),
            use_batch=safe_bool(source.get("use_batch", False), False),
            batch_max_concurrency=safe_int(source.get("batch_max_concurrency"), 5, 1, 50),
            batch_poll_interval=safe_int(source.get("batch_poll_interval"), 2, 1, 30),
            batch_timeout_seconds=safe_int(source.get("batch_timeout_seconds"), 120, 5, 1800),
            use_crawl=safe_bool(source.get("use_crawl", False), False),
            crawl_limit=safe_int(source.get("crawl_limit"), 10, 1, 1000),
            crawl_max_depth=safe_int(source.get("crawl_max_depth"), 2, 1, 20),
            crawl_allow_external_links=safe_bool(source.get("crawl_allow_external_links", False), False),
            crawl_poll_interval=safe_int(source.get("crawl_poll_interval"), 2, 1, 30),
            crawl_timeout_seconds=safe_int(source.get("crawl_timeout_seconds"), 180, 5, 3600),
            use_parse=safe_bool(source.get("use_parse", False), False),
            use_interact=safe_bool(source.get("use_interact", False), False),
            interact_prompt=clean_text(source.get("interact_prompt") or "", 2000),
            interact_code=clean_text(source.get("interact_code") or "", 5000),
            interact_language=str(source.get("interact_language") or "node").strip() or "node",
            interact_timeout_seconds=safe_int(source.get("interact_timeout_seconds"), 60, 1, 300),
            interact_wait_ms=safe_int(source.get("interact_wait_ms"), 0, 0, 60000),
            timeout_seconds=safe_int(source.get("timeout_seconds"), 45, 5, 300),
            max_retries=safe_int(source.get("max_retries"), 2, 1, 5),
        )

    def is_cloud_service(self):
        host = (urlparse(self.base_url).hostname or "").lower()
        return host.endswith("api.firecrawl.dev")

    def is_usable(self):
        return self.enabled and (bool(self.api_key) or not self.is_cloud_service())

    def safe_dict(self):
        return {
            "enabled": self.enabled,
            "api_key_present": bool(self.api_key),
            "base_url": self.base_url,
            "formats": list(self.formats),
            "only_main_content": self.only_main_content,
            "use_map": self.use_map,
            "map_limit": self.map_limit,
            "use_search": self.use_search,
            "search_query": self.search_query,
            "search_limit": self.search_limit,
            "search_sources": list(self.search_sources),
            "use_extract": self.use_extract,
            "extract_prompt": self.extract_prompt,
            "extract_schema_present": bool(self.extract_schema),
            "extract_enable_web_search": self.extract_enable_web_search,
            "extract_poll_interval": self.extract_poll_interval,
            "extract_timeout_seconds": self.extract_timeout_seconds,
            "use_batch": self.use_batch,
            "batch_max_concurrency": self.batch_max_concurrency,
            "batch_poll_interval": self.batch_poll_interval,
            "batch_timeout_seconds": self.batch_timeout_seconds,
            "use_crawl": self.use_crawl,
            "crawl_limit": self.crawl_limit,
            "crawl_max_depth": self.crawl_max_depth,
            "crawl_allow_external_links": self.crawl_allow_external_links,
            "crawl_poll_interval": self.crawl_poll_interval,
            "crawl_timeout_seconds": self.crawl_timeout_seconds,
            "use_parse": self.use_parse,
            "use_interact": self.use_interact,
            "interact_prompt": self.interact_prompt,
            "interact_code_present": bool(self.interact_code),
            "interact_language": self.interact_language,
            "interact_timeout_seconds": self.interact_timeout_seconds,
            "interact_wait_ms": self.interact_wait_ms,
            "timeout_seconds": self.timeout_seconds,
        }


class FirecrawlClient:
    def __init__(self, config: FirecrawlConfig, transport: Optional[Callable[[str, dict, dict, int], dict]] = None):
        self.config = config
        self.transport = transport

    def endpoint_url(self, endpoint):
        endpoint = str(endpoint or "")
        base = urlparse(self.config.base_url)
        parsed_endpoint = urlparse(endpoint)
        if parsed_endpoint.netloc:
            path = parsed_endpoint.path or "/"
            return urlunparse((base.scheme or "https", base.netloc, path, "", parsed_endpoint.query, ""))
        endpoint_path = f"/{endpoint.lstrip('/')}"
        if base.path.rstrip("/").endswith("/v2") and endpoint_path.startswith("/v2/"):
            endpoint_path = endpoint_path[3:]
        base_url = self.config.base_url if self.config.base_url.endswith("/") else f"{self.config.base_url}/"
        return urljoin(base_url, endpoint_path.lstrip("/"))

    def post_json(self, endpoint, payload):
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "UniversalWebCollector-FirecrawlFusion/1.0",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        payload = dict(payload or {})
        payload.setdefault("origin", "universal-web-collector")
        if self.transport:
            return self.transport(endpoint, payload, headers, self.config.timeout_seconds)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return self.request_json("POST", endpoint, headers, body)

    def get_json(self, endpoint):
        headers = {
            "User-Agent": "UniversalWebCollector-FirecrawlFusion/1.0",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        if self.transport:
            return self.transport(endpoint, {}, headers, self.config.timeout_seconds)
        return self.request_json("GET", endpoint, headers, None)

    def delete_json(self, endpoint):
        headers = {
            "User-Agent": "UniversalWebCollector-FirecrawlFusion/1.0",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        if self.transport:
            return self.transport(endpoint, {}, headers, self.config.timeout_seconds)
        return self.request_json("DELETE", endpoint, headers, None)

    def request_json(self, method, endpoint, headers, body):
        from core_api_gateway import get_gateway, GatewayError
        url = self.endpoint_url(endpoint)
        try:
            # body is None | dict (JSON) | bytes (multipart) — gateway handles all
            return get_gateway().request_json(
                method, url, payload=body, headers=headers,
                timeout=self.config.timeout_seconds,
            )
        except (GatewayError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Firecrawl 请求失败：{exc}") from exc

    def post_multipart(self, endpoint, fields, files):
        boundary = f"----UniversalFirecrawl{uuid.uuid4().hex}"
        body_parts = []
        for name, value in (fields or {}).items():
            body_parts.append(f"--{boundary}\r\n".encode("utf-8"))
            body_parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
            body_parts.append(str(value).encode("utf-8"))
            body_parts.append(b"\r\n")
        for name, file_info in (files or {}).items():
            filename, content, content_type = file_info
            body_parts.append(f"--{boundary}\r\n".encode("utf-8"))
            body_parts.append(
                (
                    f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                    f"Content-Type: {content_type or 'application/octet-stream'}\r\n\r\n"
                ).encode("utf-8")
            )
            body_parts.append(content)
            body_parts.append(b"\r\n")
        body_parts.append(f"--{boundary}--\r\n".encode("utf-8"))
        body = b"".join(body_parts)
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "UniversalWebCollector-FirecrawlFusion/1.0",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        if self.transport:
            return self.transport(endpoint, {"fields": fields or {}, "files": files or {}}, headers, self.config.timeout_seconds)
        return self.request_json("POST", endpoint, headers, body)

    def scrape(self, url):
        payload = {
            "url": url,
            "formats": list(self.config.formats),
            "onlyMainContent": bool(self.config.only_main_content),
            "timeout": int(self.config.timeout_seconds * 1000),
        }
        if self.config.interact_wait_ms:
            payload["waitFor"] = int(self.config.interact_wait_ms)
        response = self.post_json("/v2/scrape", payload)
        if not response.get("success", False):
            raise RuntimeError(response.get("error") or "Firecrawl scrape failed")
        data = response.get("data") or {}
        job_id = response.get("id") or response.get("jobId") or response.get("job_id")
        if job_id and isinstance(data, dict):
            data = dict(data)
            data["firecrawl_job_id"] = job_id
        return data

    def map(self, url):
        payload = {
            "url": url,
            "limit": int(self.config.map_limit),
            "ignoreQueryParameters": True,
        }
        response = self.post_json("/v2/map", payload)
        if not response.get("success", False):
            raise RuntimeError(response.get("error") or "Firecrawl map failed")
        links = response.get("links")
        if links is None and isinstance(response.get("data"), dict):
            links = response.get("data", {}).get("links")
        return links or []

    def search(self, query=None, limit=None, sources=None):
        query = clean_text(query or self.config.search_query, 500)
        if not query:
            return []
        search_limit = max(1, min(100, int(limit or self.config.search_limit or 5)))
        payload = {
            "query": query,
            "limit": search_limit,
            "sources": list(sources or self.config.search_sources or ["web"]),
            "ignoreInvalidURLs": True,
            "timeout": int(self.config.timeout_seconds * 1000),
        }
        response = self.post_json("/v2/search", payload)
        if not response.get("success", False):
            raise RuntimeError(response.get("error") or "Firecrawl search failed")
        data = response.get("data") or {}
        return normalize_firecrawl_search_results(data)

    def start_extract(self, urls, prompt=None, schema=None):
        payload = {
            "urls": [url for url in (urls or []) if url],
            "ignoreInvalidURLs": True,
            "enableWebSearch": bool(self.config.extract_enable_web_search),
            "showSources": True,
            "scrapeOptions": {
                "formats": list(self.config.formats),
                "onlyMainContent": bool(self.config.only_main_content),
            },
        }
        prompt = clean_text(prompt or self.config.extract_prompt, 2000)
        schema = schema if schema is not None else self.config.extract_schema
        if prompt:
            payload["prompt"] = prompt
        if isinstance(schema, dict) and schema:
            payload["schema"] = schema
        response = self.post_json("/v2/extract", payload)
        if not response.get("success", True) and not response.get("id"):
            raise RuntimeError(response.get("error") or "Firecrawl extract failed")
        return response

    def get_extract_status(self, job_id):
        if not job_id:
            return {}
        response = self.get_json(f"/v2/extract/{job_id}")
        if not response.get("success", True) and response.get("status") not in ("completed", "processing", "scraping", "failed", "cancelled"):
            raise RuntimeError(response.get("error") or "Firecrawl extract status failed")
        return response

    def cancel_job(self, endpoint, job_id):
        if not endpoint or not job_id:
            return {"cancel_requested": False, "cancel_error": "missing endpoint or job id"}
        try:
            response = self.delete_json(f"{endpoint.rstrip('/')}/{job_id}")
            return {"cancel_requested": True, "cancel_response": response}
        except Exception as exc:
            return {"cancel_requested": False, "cancel_error": str(exc)}

    def extract(self, urls, prompt=None, schema=None):
        started = self.start_extract(urls, prompt=prompt, schema=schema)
        job_id = started.get("id") or started.get("jobId") or started.get("job_id")
        if not job_id:
            return normalize_extract_payload(started)
        deadline = time.time() + max(5, int(self.config.extract_timeout_seconds or 60))
        status = started
        while time.time() <= deadline:
            status = self.get_extract_status(job_id)
            if status.get("status") in ("completed", "failed", "cancelled") or status.get("data") is not None:
                return normalize_extract_payload(status)
            time.sleep(max(1, int(self.config.extract_poll_interval or 2)))
        status = dict(status or {})
        status["status"] = "timeout"
        status.update(self.cancel_job("/v2/extract", job_id))
        return normalize_extract_payload(status)

    def start_batch_scrape(self, urls):
        payload = {
            "urls": [url for url in (urls or []) if url],
            "formats": list(self.config.formats),
            "onlyMainContent": bool(self.config.only_main_content),
            "ignoreInvalidURLs": True,
            "maxConcurrency": int(self.config.batch_max_concurrency),
            "integration": "universal-web-collector",
        }
        response = self.post_json("/v2/batch/scrape", payload)
        if not response.get("success", True) and not response.get("id"):
            raise RuntimeError(response.get("error") or "Firecrawl batch scrape failed")
        return response

    def get_batch_scrape_status(self, job_id):
        if not job_id:
            return {}
        response = self.get_json(f"/v2/batch/scrape/{job_id}")
        if not response.get("success", True) and response.get("status") not in ("completed", "scraping", "processing", "failed", "cancelled"):
            raise RuntimeError(response.get("error") or "Firecrawl batch scrape status failed")
        return response

    def batch_scrape(self, urls):
        started = self.start_batch_scrape(urls)
        job_id = started.get("id") or started.get("jobId") or started.get("job_id")
        if not job_id:
            return normalize_job_payload(started)
        return self.wait_for_job(
            job_id,
            status_getter=self.get_batch_scrape_status,
            poll_interval=self.config.batch_poll_interval,
            timeout_seconds=self.config.batch_timeout_seconds,
            cancel_endpoint="/v2/batch/scrape",
        )

    def start_crawl(self, url):
        payload = {
            "url": url,
            "limit": int(self.config.crawl_limit),
            "maxDiscoveryDepth": int(self.config.crawl_max_depth),
            "allowExternalLinks": bool(self.config.crawl_allow_external_links),
            "ignoreQueryParameters": True,
            "deduplicateSimilarURLs": True,
            "scrapeOptions": {
                "formats": list(self.config.formats),
                "onlyMainContent": bool(self.config.only_main_content),
            },
            "integration": "universal-web-collector",
        }
        response = self.post_json("/v2/crawl", payload)
        if not response.get("success", True) and not response.get("id"):
            raise RuntimeError(response.get("error") or "Firecrawl crawl failed")
        return response

    def get_crawl_status(self, job_id):
        if not job_id:
            return {}
        response = self.get_json(f"/v2/crawl/{job_id}")
        if not response.get("success", True) and response.get("status") not in ("completed", "scraping", "processing", "failed", "cancelled"):
            raise RuntimeError(response.get("error") or "Firecrawl crawl status failed")
        return response

    def crawl(self, url):
        started = self.start_crawl(url)
        job_id = started.get("id") or started.get("jobId") or started.get("job_id")
        if not job_id:
            return normalize_job_payload(started)
        return self.wait_for_job(
            job_id,
            status_getter=self.get_crawl_status,
            poll_interval=self.config.crawl_poll_interval,
            timeout_seconds=self.config.crawl_timeout_seconds,
            cancel_endpoint="/v2/crawl",
        )

    def wait_for_job(self, job_id, status_getter, poll_interval=2, timeout_seconds=120, cancel_endpoint=""):
        deadline = time.time() + max(5, int(timeout_seconds or 120))
        status = {}
        while time.time() <= deadline:
            status = status_getter(job_id)
            if status.get("status") in ("completed", "failed", "cancelled"):
                return normalize_job_payload(status)
            if status.get("data") and not status.get("status"):
                return normalize_job_payload(status)
            time.sleep(max(1, int(poll_interval or 2)))
        status = dict(status or {})
        status["status"] = "timeout"
        if cancel_endpoint:
            status.update(self.cancel_job(cancel_endpoint, job_id))
        return normalize_job_payload(status)

    def parse_file(self, file_path):
        filename = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        if file_size > FIRECRAWL_MAX_PARSE_FILE_BYTES:
            raise RuntimeError(f"Firecrawl Parse 文件过大：{file_size} 字节，最大支持 {FIRECRAWL_MAX_PARSE_FILE_BYTES} 字节")
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        with open(file_path, "rb") as f:
            content = f.read()
        fields = {
            "options": json.dumps(
                {
                    "formats": list(self.config.formats),
                    "onlyMainContent": bool(self.config.only_main_content),
                    "origin": "universal-web-collector",
                },
                ensure_ascii=False,
            )
        }
        response = self.post_multipart("/v2/parse", fields, {"file": (filename, content, content_type)})
        if not response.get("success", False):
            raise RuntimeError(response.get("error") or "Firecrawl parse failed")
        return response.get("data") or {}

    def parse_file_to_table(self, file_path, instruction=""):
        document = self.parse_file(file_path)
        record = firecrawl_document_to_record(document, f"file:///{os.path.abspath(file_path)}", template_name="Firecrawl Parse")
        rows = [["标题", record.get("title", "")], ["正文", record.get("body", "")]]
        for link in record.get("links", [])[:100]:
            rows.append(["链接", link.get("url", "") if isinstance(link, dict) else str(link)])
        for image in record.get("images", [])[:100]:
            rows.append(["图片", image.get("url", "") if isinstance(image, dict) else str(image)])
        for row in extract_data_to_rows(document.get("json") or document.get("metadata") or {}):
            rows.append(row)
        return {
            "columns": ["字段", "值"],
            "rows": [[clean_text(item[0], 300), clean_text(item[1], 5000)] for item in rows if item and item[1]],
            "source": "firecrawl_parse",
            "instruction": instruction,
        }

    def interact(self, job_id, prompt=None, code=None):
        prompt = clean_text(prompt if prompt is not None else self.config.interact_prompt, 2000)
        code = clean_text(code if code is not None else self.config.interact_code, 5000)
        if not job_id:
            raise RuntimeError("Firecrawl interact 缺少 scrape job id")
        if not prompt and not code:
            raise RuntimeError("Firecrawl interact 缺少 prompt 或 code")
        payload = {
            "language": self.config.interact_language if self.config.interact_language in ("python", "node", "bash") else "node",
            "timeout": int(self.config.interact_timeout_seconds),
            "origin": "universal-web-collector",
        }
        if prompt:
            payload["prompt"] = prompt
        if code:
            payload["code"] = code
        response = self.post_json(f"/v2/scrape/{job_id}/interact", payload)
        if not response.get("success", False):
            raise RuntimeError(response.get("error") or "Firecrawl interact failed")
        return normalize_interact_payload(response)

    def stop_interaction(self, job_id):
        response = self.delete_json(f"/v2/scrape/{job_id}/interact")
        return normalize_interact_stop_payload(response)


def metadata_value(metadata, *keys):
    if not isinstance(metadata, dict):
        return ""
    for key in keys:
        if key in metadata and metadata.get(key) not in (None, ""):
            value = metadata.get(key)
            if isinstance(value, list):
                return clean_text(", ".join(str(item) for item in value if item), 1000)
            return clean_text(value, 1000)
    return ""


def first_markdown_heading(markdown):
    for line in str(markdown or "").splitlines():
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
        if match:
            return clean_text(match.group(1), 300)
    return ""


def html_text(html):
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return clean_text(unescape(soup.get_text("\n", strip=True)), 20000)


def links_from_firecrawl(value, base_url):
    links = []
    seen = set()
    for item in value or []:
        if isinstance(item, dict):
            raw_url = item.get("url") or item.get("href") or ""
            text = item.get("text") or item.get("title") or item.get("description") or ""
        else:
            raw_url = str(item or "")
            text = ""
        link_url = normalize_url(raw_url, base_url)
        if link_url and link_url not in seen:
            links.append({"url": link_url, "text": clean_text(text, 300)})
            seen.add(link_url)
    return links


def links_from_html(html, base_url):
    soup = BeautifulSoup(html or "", "html.parser")
    return links_from_firecrawl(
        [
            {"url": tag.get("href", ""), "text": tag.get_text(" ", strip=True) or tag.get("title", "")}
            for tag in soup.select("a[href]")
        ],
        base_url,
    )


def images_from_firecrawl(document, metadata, html, base_url):
    values = []
    raw_images = document.get("images") or document.get("image") or []
    if isinstance(raw_images, (str, dict)):
        raw_images = [raw_images]
    for item in raw_images or []:
        if isinstance(item, dict):
            values.append({"url": item.get("url") or item.get("src") or "", "alt": item.get("alt", "")})
        else:
            values.append({"url": str(item or ""), "alt": ""})
    for key in ("ogImage", "og_image", "image", "twitterImage", "twitter_image"):
        if isinstance(metadata, dict) and metadata.get(key):
            values.append({"url": metadata.get(key), "alt": ""})
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup.select("img[src], img[data-src]"):
        values.append({"url": tag.get("src") or tag.get("data-src") or "", "alt": tag.get("alt", "")})
    images = []
    seen = set()
    for item in values:
        image_url = normalize_url(item.get("url", ""), base_url)
        if image_url and image_url not in seen and not image_url.startswith("data:"):
            images.append({"url": image_url, "alt": clean_text(item.get("alt", ""), 300)})
            seen.add(image_url)
    return images


def normalize_firecrawl_search_results(data):
    if isinstance(data, list):
        buckets = {"web": data}
    elif isinstance(data, dict):
        buckets = data
    else:
        buckets = {}
    results = []
    seen = set()
    for source_type in ("web", "news", "images"):
        for item in buckets.get(source_type) or []:
            if isinstance(item, dict):
                raw_url = (
                    item.get("url")
                    or item.get("link")
                    or item.get("sourceURL")
                    or item.get("sourceUrl")
                    or item.get("imageUrl")
                    or ""
                )
                title = item.get("title") or item.get("name") or item.get("alt") or ""
                description = item.get("description") or item.get("snippet") or item.get("markdown") or ""
            else:
                raw_url = str(item or "")
                title = ""
                description = ""
            url = normalize_url(raw_url)
            if not url or url in seen:
                continue
            results.append(
                {
                    "url": url,
                    "title": clean_text(title, 300),
                    "description": clean_text(description, 800),
                    "source": source_type,
                }
            )
            seen.add(url)
    return results


def normalize_extract_payload(payload):
    payload = dict(payload or {})
    if "data" in payload:
        data = payload.get("data")
    elif "extract" in payload:
        data = payload.get("extract")
    else:
        data = payload
    result = {
        "status": payload.get("status", "completed" if data else ""),
        "data": data,
        "sources": payload.get("sources") or payload.get("source") or [],
        "error": payload.get("error") or "",
    }
    for key in ("cancel_requested", "cancel_error", "cancel_response"):
        if key in payload:
            result[key] = payload.get(key)
    return result


def normalize_job_payload(payload):
    payload = dict(payload or {})
    result = {
        "status": payload.get("status", "completed" if payload.get("data") else ""),
        "completed": int(payload.get("completed") or len(payload.get("data") or [])),
        "total": int(payload.get("total") or len(payload.get("data") or [])),
        "credits_used": payload.get("creditsUsed", payload.get("credits_used", 0)),
        "next": payload.get("next") or "",
        "data": payload.get("data") or [],
        "error": payload.get("error") or "",
    }
    for key in ("cancel_requested", "cancel_error", "cancel_response"):
        if key in payload:
            result[key] = payload.get(key)
    return result


def normalize_interact_payload(payload):
    payload = dict(payload or {})
    return {
        "success": bool(payload.get("success", True)),
        "output": payload.get("output") or payload.get("stdout") or payload.get("result") or "",
        "error": payload.get("error") or payload.get("stderr") or "",
        "exit_code": payload.get("exitCode", payload.get("exit_code", 0)),
        "live_view_url": payload.get("liveViewUrl", payload.get("live_view_url", "")),
        "interactive_live_view_url": payload.get("interactiveLiveViewUrl", payload.get("interactive_live_view_url", "")),
    }


def normalize_interact_stop_payload(payload):
    payload = dict(payload or {})
    return {
        "success": bool(payload.get("success", True)),
        "status": payload.get("status") or "",
        "session_duration_ms": payload.get("sessionDurationMs", payload.get("session_duration_ms", 0)),
        "credits_billed": payload.get("creditsBilled", payload.get("credits_billed", 0)),
        "error": payload.get("error") or "",
    }


def extract_data_to_rows(data, prefix=""):
    rows = []
    if isinstance(data, dict):
        for key, value in data.items():
            label = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, (dict, list)):
                rows.extend(extract_data_to_rows(value, label))
            else:
                rows.append([label, clean_text(value, 2000)])
    elif isinstance(data, list):
        for index, value in enumerate(data):
            label = f"{prefix}[{index}]" if prefix else f"[{index}]"
            if isinstance(value, (dict, list)):
                rows.extend(extract_data_to_rows(value, label))
            else:
                rows.append([label, clean_text(value, 2000)])
    elif data not in (None, ""):
        rows.append([prefix or "value", clean_text(data, 2000)])
    return rows


def merge_firecrawl_extract_record(record, extract_payload):
    record = dict(record or {})
    payload = normalize_extract_payload(extract_payload)
    data = payload.get("data")
    if data in (None, "", [], {}):
        if payload.get("error"):
            record["error"] = clean_text("; ".join(filter(None, [record.get("error", ""), payload.get("error", "")])), 2000)
        return record
    rows = extract_data_to_rows(data)
    if rows:
        tables = list(record.get("tables") or [])
        tables.append([["字段", "值"]] + rows[:200])
        record["tables"] = tables
    section = "Firecrawl 结构化抽取：\n" + clean_text(json.dumps(data, ensure_ascii=False, indent=2), 6000)
    record["body"] = clean_text("\n\n".join([record.get("body", ""), section]).strip(), 20000)
    if isinstance(data, dict):
        title = data.get("title") or data.get("name") or data.get("headline")
        price = data.get("price") or data.get("amount")
        author = data.get("author") or data.get("seller") or data.get("company") or data.get("source")
        published_time = data.get("published_time") or data.get("publishedTime") or data.get("date") or data.get("time")
        if title and not record.get("title"):
            record["title"] = clean_text(title, 300)
        if price and not record.get("price"):
            record["price"] = clean_text(price, 200)
        if author and not record.get("author"):
            record["author"] = clean_text(author, 300)
        if published_time and not record.get("published_time"):
            record["published_time"] = clean_text(published_time, 300)
    record["firecrawl_extract"] = payload
    return record


def merge_firecrawl_interact_record(record, interact_payload):
    record = dict(record or {})
    payload = normalize_interact_payload(interact_payload)
    output = clean_text(payload.get("output", ""), 5000)
    error = clean_text(payload.get("error", ""), 2000)
    if output:
        record["body"] = clean_text(
            "\n\n".join([record.get("body", ""), "Firecrawl 交互结果：\n" + output]).strip(),
            20000,
        )
        tables = list(record.get("tables") or [])
        tables.append([["字段", "值"], ["交互输出", output]])
        record["tables"] = tables
    if error:
        record["error"] = clean_text("; ".join(filter(None, [record.get("error", ""), f"Interact: {error}"])), 2000)
    record["firecrawl_interact"] = payload
    return record


def firecrawl_document_to_record(document, fallback_url, template_name="Firecrawl"):
    document = dict(document or {})
    metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
    source_url = (
        metadata_value(metadata, "sourceURL", "sourceUrl", "source_url", "url", "ogUrl", "og_url")
        or clean_text(document.get("url") or "", 1000)
        or fallback_url
    )
    url = normalize_url(source_url, fallback_url) or normalize_url(fallback_url)
    markdown = clean_text(document.get("markdown") or document.get("content") or "", 20000)
    html = document.get("html") or document.get("rawHtml") or document.get("raw_html") or ""
    body = markdown or html_text(html)
    title = (
        metadata_value(metadata, "title", "ogTitle", "og_title")
        or clean_text(document.get("title") or "", 300)
        or first_markdown_heading(markdown)
    )
    if not title and html:
        soup = BeautifulSoup(html, "html.parser")
        title = clean_text((soup.title.get_text(" ", strip=True) if soup.title else "") or "", 300)
        if not title:
            heading = soup.find(["h1", "h2"])
            title = clean_text(heading.get_text(" ", strip=True) if heading else "", 300)
    links = links_from_firecrawl(document.get("links") or [], url)
    for link in links_from_html(html, url):
        if link.get("url") and link.get("url") not in {item.get("url") for item in links}:
            links.append(link)
    record = {
        "collected_at": now_text(),
        "url": url,
        "domain": url_domain(url),
        "template_name": f"{template_name or '默认模板'} + Firecrawl",
        "title": title,
        "price": clean_text(document.get("price") or "", 200),
        "published_time": metadata_value(metadata, "publishedTime", "published_time", "modifiedTime", "modified_time"),
        "author": metadata_value(metadata, "author", "ogSiteName", "og_site_name", "siteName", "site_name"),
        "body": body,
        "images": images_from_firecrawl(document, metadata, html, url),
        "links": links,
        "tables": [],
        "error": metadata_value(metadata, "error"),
        "firecrawl_metadata": metadata,
    }
    return record
