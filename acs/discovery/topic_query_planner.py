"""TopicQueryPlanner — expand topic + keywords into diverse search queries.

Produces combinations that cover different angles:
  topic alone, topic+keyword pairs, keyword combos, type-qualified queries.
Never generates bypass/proxy/login/captcha related queries.
"""
from typing import List
from itertools import combinations


SYNONYMS = {
    "案例": ["实例", "示范", "典型", "经验", "做法"],
    "政策": ["法规", "规定", "制度", "条例", "办法", "通知", "公告"],
    "数据": ["统计", "指标", "报告", "年报"],
    "技术": ["工艺", "方法", "方案", "路线"],
    "治理": ["管控", "管理", "处理", "控制", "减排"],
    "公开": ["公示", "发布", "公告"],
}
BLOCKED_WORDS = {"爬虫", "抓取", "spider", "scrape", "bypass", "proxy", "代理",
                 "绕过", "captcha", "验证码", "破解", "login", "cookie", "token"}


class TopicQueryPlanner:
    """Expand a topic into multiple search queries covering different angles.

    Usage:
        planner = TopicQueryPlanner()
        queries = planner.plan(topic="园区废气治理案例",
                               keywords=["VOCs","活性炭","整改报告"],
                               content_type="", limit=15)
    """

    def __init__(self):
        self.max_queries = 15

    def _expand_keywords(self, keywords: List[str]) -> List[str]:
        """Expand keywords with synonyms where applicable."""
        expanded = list(keywords)
        for kw in keywords:
            for key, syns in SYNONYMS.items():
                if kw.endswith(key) or key in kw:
                    for s in syns:
                        if s not in expanded and s not in keywords:
                            expanded.append(s)
        return list(dict.fromkeys(expanded))  # dedup, preserve order

    def _is_safe(self, query: str) -> bool:
        """Reject queries containing blocked words."""
        lower = query.lower()
        for bw in BLOCKED_WORDS:
            if bw.lower() in lower:
                return False
        return True

    def plan(self, topic: str, keywords: List[str],
             content_type: str = "", limit: int = 15,
             exclude_words: List[str] = None,
             time_range: str = "",
             language: str = "zh") -> List[str]:
        """Generate diverse search queries from topic and keywords.

        Args:
            topic: Main topic (e.g., "园区废气治理案例")
            keywords: Keywords list (e.g., ["VOCs","活性炭"])
            content_type: Optional content type filter
            limit: Max number of queries to return
            exclude_words: Words to exclude from queries
            time_range: Optional time range hint
            language: Query language (zh/en)

        Returns:
            List of query strings
        """
        if not topic and not keywords:
            return []

        expanded = self._expand_keywords(list(keywords)) if keywords else []
        all_words = ([topic] if topic else []) + expanded
        exclude = set(exclude_words or [])

        queries = []

        # 1. Topic alone
        if topic and topic not in exclude:
            q = topic.strip()
            if self._is_safe(q):
                queries.append(q)

        # 2. Topic + each expanded keyword
        if topic:
            for kw in expanded[:8]:
                q = f"{topic} {kw}".strip()
                if q not in queries and self._is_safe(q):
                    queries.append(q)

        # 3. Keyword pairs
        for i in range(min(6, len(expanded))):
            for j in range(i + 1, min(6, len(expanded))):
                q = f"{expanded[i]} {expanded[j]}".strip()
                if q not in queries and self._is_safe(q):
                    queries.append(q)

        # 4. Topic + keyword pair combos
        if topic:
            for i, k1 in enumerate(expanded[:4]):
                for k2 in expanded[i+1:min(5, len(expanded))]:
                    q = f"{topic} {k1} {k2}".strip()
                    if q not in queries and self._is_safe(q):
                        queries.append(q)

        # 5. Content-type qualified
        if content_type:
            type_hints = {
                "pdf": "filetype:pdf",
                "doc": "filetype:doc",
                "news": "新闻",
                "policy": "政策 OR 公告 OR 通知",
                "case": "案例",
                "data": "数据 OR 统计",
            }
            hint = type_hints.get(content_type, content_type)
            if topic:
                q = f"{topic} {hint}".strip()
                if q not in queries and self._is_safe(q):
                    queries.append(q)

        # 6. Time-qualified if specified
        if time_range and topic:
            q = f"{topic} {time_range}".strip()
            if q not in queries and self._is_safe(q):
                queries.append(q)

        # Remove duplicates while preserving order
        seen = set()
        result = []
        for q in queries:
            if q not in seen and q not in exclude:
                seen.add(q)
                result.append(q)
        return result[:limit]
