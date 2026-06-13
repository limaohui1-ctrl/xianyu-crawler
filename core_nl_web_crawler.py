"""Async natural-language web crawling pipeline.

Fixed black-box architecture:
1. LLM derives search query + extraction schema from user intent.
2. Search API returns relevant URLs.
3. Jina Reader converts pages to Markdown.
4. LLM merges Markdown into strict structured JSON.
"""

import asyncio
import json
import os
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx


DEFAULT_SYSTEM_INTENT_PROMPT = (
    "你是全网采集任务规划器。"
    "根据用户自然语言需求，返回一个 JSON 对象，包含 search_query、schema 和 extraction_notes。"
    "schema 必须是一个 JSON Schema 风格对象，根层至少包含 type='array' 与 items.properties。"
    "search_query 必须适合搜索引擎直接检索。"
    "不要返回 Markdown，不要解释。"
)

DEFAULT_SYSTEM_MERGE_PROMPT = (
    "你是网页信息抽取与合流专家。"
    "你会收到多个网页 Markdown、目标 schema 与抽取说明。"
    "请过滤广告、导航、无关文案，严格按 schema 抽取并合并结果。"
    "返回 JSON 对象，根键必须为 items，值为数组。"
    "不要返回 Markdown，不要返回解释。"
)


class AsyncNaturalLanguageWebCrawler:
    """Natural-language driven whole-web crawler using search + Jina + LLM."""

    def __init__(
        self,
        *,
        llm_base_url: Optional[str] = None,
        llm_api_key: Optional[str] = None,
        llm_model: Optional[str] = None,
        search_provider: Optional[str] = None,
        search_api_key: Optional[str] = None,
        search_endpoint: Optional[str] = None,
        timeout_seconds: float = 20.0,
        page_timeout_seconds: float = 12.0,
        max_search_results: int = 5,
        demo_mode: bool = False,
    ) -> None:
        self.llm_base_url = (llm_base_url or os.getenv("NL_CRAWLER_LLM_BASE_URL") or "").rstrip("/")
        self.llm_api_key = llm_api_key or os.getenv("NL_CRAWLER_LLM_API_KEY") or ""
        self.llm_model = llm_model or os.getenv("NL_CRAWLER_LLM_MODEL") or ""
        self.search_provider = (search_provider or os.getenv("NL_CRAWLER_SEARCH_PROVIDER") or "serper").strip().lower()
        self.search_api_key = search_api_key or os.getenv("NL_CRAWLER_SEARCH_API_KEY") or ""
        self.search_endpoint = (search_endpoint or os.getenv("NL_CRAWLER_SEARCH_ENDPOINT") or "").strip()
        self.timeout_seconds = timeout_seconds
        self.page_timeout_seconds = page_timeout_seconds
        self.max_search_results = max(1, int(max_search_results))
        self.demo_mode = bool(demo_mode)

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=True,
            headers={
                "User-Agent": "UniversalCollector-NaturalLanguageCrawler/1.0",
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.aclose()

    def require_ready(self) -> None:
        if not self.llm_base_url:
            raise RuntimeError("缺少大模型 Base URL，请配置 NL_CRAWLER_LLM_BASE_URL。")
        if not self.llm_model:
            raise RuntimeError("缺少大模型名称，请配置 NL_CRAWLER_LLM_MODEL。")
        if not self.llm_api_key:
            raise RuntimeError("缺少大模型 API Key，请配置 NL_CRAWLER_LLM_API_KEY。")
        if self.search_provider not in {"serper", "bing"}:
            raise RuntimeError("NL_CRAWLER_SEARCH_PROVIDER 仅支持 serper 或 bing。")
        if not self.search_api_key:
            raise RuntimeError("缺少搜索 API Key，请配置 NL_CRAWLER_SEARCH_API_KEY。")

    async def run(self, user_prompt: str) -> Dict[str, Any]:
        if self.demo_mode:
            return self._demo_result(user_prompt)
        self.require_ready()
        user_prompt = (user_prompt or "").strip()
        if not user_prompt:
            raise RuntimeError("用户输入不能为空。")

        plan = await self._derive_intent_and_schema(user_prompt)
        search_query = (plan.get("search_query") or "").strip()
        schema = plan.get("schema") or {}
        extraction_notes = plan.get("extraction_notes") or ""
        if not search_query:
            raise RuntimeError("大模型未返回有效 search_query。")
        if not isinstance(schema, dict) or not schema:
            raise RuntimeError("大模型未返回有效 schema。")

        urls = await self._search_urls(search_query)
        markdown_pages = await self._fetch_markdown_pages(urls)
        merged = await self._merge_markdown_to_structured_json(
            user_prompt=user_prompt,
            search_query=search_query,
            schema=schema,
            extraction_notes=extraction_notes,
            markdown_pages=markdown_pages,
        )
        items = merged.get("items")
        if not isinstance(items, list):
            raise RuntimeError(f"最终返回不是标准 items 数组：{merged}")
        return {
            "query": search_query,
            "schema": schema,
            "urls": urls,
            "pages": markdown_pages,
            "items": items,
        }


    def _demo_result(self, user_prompt: str) -> Dict[str, Any]:
        query = compact_query = (user_prompt or "AI 智能体框架").strip()[:80]
        schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "summary": {"type": "string"},
                    "source_url": {"type": "string"},
                },
            },
        }
        urls = [
            "https://example.com/agent-framework-a",
            "https://example.com/agent-framework-b",
            "https://example.com/agent-framework-c",
        ]
        pages = [
            {"url": urls[0], "markdown": "# Agent Framework A\n\n主打工作流编排与工具调用。"},
            {"url": urls[1], "markdown": "# Agent Framework B\n\n主打多智能体协作与记忆。"},
            {"url": urls[2], "markdown": "# Agent Framework C\n\n主打本地部署与可观测性。"},
        ]
        items = [
            {"name": "Agent Framework A", "summary": "主打工作流编排与工具调用。", "source_url": urls[0]},
            {"name": "Agent Framework B", "summary": "主打多智能体协作与记忆。", "source_url": urls[1]},
            {"name": "Agent Framework C", "summary": "主打本地部署与可观测性。", "source_url": urls[2]},
        ]
        return {"query": compact_query, "schema": schema, "urls": urls, "pages": pages, "items": items, "demo_mode": True}

    async def _derive_intent_and_schema(self, user_prompt: str) -> Dict[str, Any]:
        payload = {
            "task": "根据用户需求生成搜索词和抽取 schema。",
            "requirements": {
                "search_query": "简洁、精准、适合搜索引擎",
                "schema": "返回 JSON Schema 风格对象，根层 type=array，items.type=object，items.properties 定义字段",
                "extraction_notes": "补充抽取约束、去重规则、时间/排序偏好",
            },
            "user_prompt": user_prompt,
        }
        return await self._call_llm_json(
            system_prompt=DEFAULT_SYSTEM_INTENT_PROMPT,
            user_prompt=json.dumps(payload, ensure_ascii=False),
        )

    async def _search_urls(self, query: str) -> List[str]:
        if self.search_provider == "serper":
            return await self._search_urls_serper(query)
        return await self._search_urls_bing(query)

    async def _search_urls_serper(self, query: str) -> List[str]:
        url = self.search_endpoint or "https://google.serper.dev/search"
        response = await self._client.post(
            url,
            headers={"X-API-KEY": self.search_api_key, "Content-Type": "application/json"},
            json={"q": query, "num": self.max_search_results},
        )
        response.raise_for_status()
        data = response.json()
        organic = data.get("organic") or []
        urls: List[str] = []
        for item in organic:
            target_url = (item.get("link") or item.get("url") or "").strip()
            if target_url and target_url not in urls:
                urls.append(target_url)
            if len(urls) >= self.max_search_results:
                break
        return urls

    async def _search_urls_bing(self, query: str) -> List[str]:
        url = self.search_endpoint or "https://api.bing.microsoft.com/v7.0/search"
        response = await self._client.get(
            url,
            headers={"Ocp-Apim-Subscription-Key": self.search_api_key},
            params={"q": query, "count": self.max_search_results, "responseFilter": "Webpages"},
        )
        response.raise_for_status()
        data = response.json()
        values = ((data.get("webPages") or {}).get("value") or [])
        urls: List[str] = []
        for item in values:
            target_url = (item.get("url") or "").strip()
            if target_url and target_url not in urls:
                urls.append(target_url)
            if len(urls) >= self.max_search_results:
                break
        return urls

    async def _fetch_markdown_pages(self, urls: List[str]) -> List[Dict[str, Any]]:
        tasks = [self._fetch_single_markdown(url) for url in urls[: self.max_search_results]]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        pages: List[Dict[str, Any]] = []
        for result in results:
            if isinstance(result, Exception):
                continue
            if result and result.get("markdown"):
                pages.append(result)
        return pages

    async def _fetch_single_markdown(self, url: str) -> Optional[Dict[str, Any]]:
        reader_url = f"https://r.jina.ai/http://{url}" if not url.startswith(("http://", "https://")) else f"https://r.jina.ai/{url}"
        try:
            response = await self._client.get(reader_url, timeout=httpx.Timeout(self.page_timeout_seconds))
            response.raise_for_status()
            markdown = (response.text or "").strip()
            if not markdown:
                return None
            return {"url": url, "markdown": markdown}
        except Exception:
            return None

    async def _merge_markdown_to_structured_json(
        self,
        *,
        user_prompt: str,
        search_query: str,
        schema: Dict[str, Any],
        extraction_notes: str,
        markdown_pages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        payload = {
            "task": "从多个网页 Markdown 中提取结构化结果并合流。",
            "user_prompt": user_prompt,
            "search_query": search_query,
            "schema": schema,
            "extraction_notes": extraction_notes,
            "pages": markdown_pages,
            "output_requirement": {"root_key": "items", "type": "array"},
        }
        return await self._call_llm_json(
            system_prompt=DEFAULT_SYSTEM_MERGE_PROMPT,
            user_prompt=json.dumps(payload, ensure_ascii=False),
        )

    async def _call_llm_json(self, *, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        url = f"{self.llm_base_url}/chat/completions"
        payload = {
            "model": self.llm_model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        response = await self._client.post(
            url,
            headers={
                "Authorization": f"Bearer {self.llm_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        try:
            raw_content = data["choices"][0]["message"]["content"]
        except Exception as exc:
            raise RuntimeError(f"大模型返回格式不符合 OpenAI 兼容格式：{data}") from exc
        if isinstance(raw_content, list):
            raw_content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in raw_content
            )
        try:
            parsed = json.loads(raw_content)
        except Exception as exc:
            raise RuntimeError(f"大模型未返回合法 JSON：{raw_content}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError(f"大模型 JSON 根节点必须是对象：{parsed}")
        return parsed


async def crawl_from_natural_language(user_prompt: str, **kwargs: Any) -> Dict[str, Any]:
    """Convenience function for one-shot use."""
    async with AsyncNaturalLanguageWebCrawler(**kwargs) as crawler:
        return await crawler.run(user_prompt)


REQUIRED_ENV_VARS = {
    "NL_CRAWLER_LLM_BASE_URL": "OpenAI 兼容大模型接口根地址，例如 https://api.openai.com/v1",
    "NL_CRAWLER_LLM_API_KEY": "大模型 API Key",
    "NL_CRAWLER_LLM_MODEL": "用于意图推导与最终结构化提取的模型名",
    "NL_CRAWLER_SEARCH_PROVIDER": "搜索服务提供商：serper 或 bing",
    "NL_CRAWLER_SEARCH_API_KEY": "搜索 API Key",
    "NL_CRAWLER_SEARCH_ENDPOINT": "可选；覆盖默认搜索接口地址",
}
