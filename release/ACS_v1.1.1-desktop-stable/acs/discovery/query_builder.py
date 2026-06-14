"""QueryBuilder — topic + keywords → search queries."""
import itertools


class QueryBuilder:
    """Build search queries from topic and keywords. Never generates bypass queries."""

    MAX_QUERIES = 10

    def build(self, topic: str, keywords: list, source_type: str = "webpage",
              limit: int = 50) -> list:
        """Generate search query strings from topic and keywords.

        Args:
            topic: The user's topic (e.g. "园区废气治理案例")
            keywords: List of keywords (e.g. ["VOCs", "活性炭", "整改报告"])
            source_type: webpage / pdf / article / policy / enterprise / product
            limit: Target number of results (used to tune query breadth)

        Returns:
            List of query strings (3-10)
        """
        kw = [k.strip() for k in keywords if k.strip()]
        topic_clean = topic.strip()

        queries = []

        # Full topic as one query
        queries.append(topic_clean)

        # Topic + each keyword
        for k in kw:
            q = f"{topic_clean} {k}"
            if q not in queries:
                queries.append(q)

        # Keyword pairs with topic
        if len(kw) >= 2:
            for a, b in itertools.combinations(kw[:5], 2):
                q = f"{a} {b}"
                if q not in queries:
                    queries.append(q)

        # Topic + source_type hint
        type_hints = {
            "webpage": "公开资料",
            "pdf": "PDF 文件",
            "article": "文章",
            "policy": "政策文件",
            "enterprise": "企业信息",
            "product": "产品资料",
        }
        hint = type_hints.get(source_type, "公开资料")
        q = f"{topic_clean} {hint}"
        if q not in queries:
            queries.append(q)

        # Deduplicate and limit
        seen = set()
        unique = []
        for q in queries:
            if q not in seen:
                seen.add(q)
                unique.append(q)

        return unique[:self.MAX_QUERIES]
