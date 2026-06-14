"""SourceDiscovery — orchestrate the full discovery → filter → rank → store pipeline.

Supports: mock, import-file, sitemap, rss providers.
"""
from typing import List, Optional
from .query_builder import QueryBuilder
from .mock_search_provider import MockSearchProvider
from .compliance_filter import ComplianceFilter
from .relevance_ranker import RelevanceRanker
from .candidate_store import CandidateStore
from .discovery_report import DiscoveryReport
from .url_safety_checker import UrlSafetyChecker


class SourceDiscovery:
    """Main orchestrator: discover → filter → rank → store → report."""

    def __init__(self, store_dir: str = "acs_data/discovery"):
        self.query_builder = QueryBuilder()
        self.mock_provider = MockSearchProvider()
        self.compliance_filter = ComplianceFilter()
        self.relevance_ranker = RelevanceRanker()
        self.url_safety = UrlSafetyChecker()
        self.store = CandidateStore(store_dir)

    def discover(self, topic: str, keywords: List[str],
                 source_type: str = "webpage",
                 provider: str = "mock",
                 limit: int = 50,
                 auto_select_allowed: bool = False,
                 extra_params: Optional[dict] = None) -> dict:
        """Run full discovery pipeline with any registered provider.

        Args:
            topic: User topic
            keywords: List of keywords
            source_type: webpage / pdf / article / etc.
            provider: 'mock' | 'import-file' | 'sitemap' | 'rss'
            limit: Max candidates to return
            auto_select_allowed: Auto-select all allowed candidates
            extra_params: Provider-specific params (input_path, sitemap_url, feed_url)

        Returns:
            dict with: report, candidates, selected_urls_path, store_path, batch_id
        """
        extra = extra_params or {}

        # 1. Get candidates from provider
        candidates = self._get_candidates(provider, topic, keywords, limit, extra)

        # 2. URL safety check
        urls = [c.url for c in candidates]
        safe_urls, unsafe = self.url_safety.filter_safe(urls)
        if unsafe:
            safe_set = set(safe_urls)
            candidates = [c for c in candidates if c.url in safe_set]

        # 3. Compliance filter
        candidates = self.compliance_filter.filter_all(candidates)

        # 4. Relevance ranking
        candidates = self.relevance_ranker.rank(candidates, topic, keywords)

        # 5. Auto-select allowed
        if auto_select_allowed:
            for c in candidates:
                if c.compliance_status == "allowed":
                    c.selected = True

        # 6. Build report
        queries = self.query_builder.build(topic, keywords, source_type, limit) \
            if provider == "mock" else []
        report = DiscoveryReport.from_candidates(
            candidates, topic=topic, keywords=keywords,
            source_type=source_type, queries_used=len(queries),
        )

        # 7. Save to store
        store_path = self.store.save(candidates, report.batch_id)

        # 8. Export selected URLs
        selected_path = self.store.export_selected_urls(candidates)

        return {
            "report": report.to_dict(),
            "candidates": [c.to_dict() for c in candidates],
            "selected_urls_path": selected_path,
            "store_path": store_path,
            "batch_id": report.batch_id,
        }

    def _get_candidates(self, provider: str, topic: str, keywords: list,
                        limit: int, extra: dict) -> list:
        """Route to the right provider."""
        if provider == "mock":
            queries = self.query_builder.build(topic, keywords, "webpage", limit)
            return self.mock_provider.search_all(queries, limit=limit)

        elif provider == "import-file":
            from .imported_search_provider import ImportedSearchProvider
            imp = ImportedSearchProvider()
            path = extra.get("input_path", "")
            if not path:
                return []
            return imp.load(path, topic=topic, keywords=keywords)[:limit]

        elif provider == "sitemap":
            from .sitemap_provider import SitemapProvider
            sm = SitemapProvider()
            sitemap_url = extra.get("sitemap_url", "")
            if not sitemap_url:
                return []
            return sm.discover(sitemap_url, topic=topic, keywords=keywords, max_urls=limit)

        elif provider == "rss":
            from .rss_provider import RssProvider
            rp = RssProvider()
            feed_url = extra.get("feed_url", "")
            if not feed_url:
                return []
            return rp.discover(feed_url, topic=topic, keywords=keywords, max_entries=limit)

        else:
            raise ValueError(f"Unknown provider: {provider}")

    def load_batch(self, batch_id: str) -> dict:
        """Load a previously saved discovery batch."""
        candidates = self.store.load(batch_id)
        if not candidates:
            return {"error": f"batch {batch_id} not found", "candidates": []}
        report = DiscoveryReport.from_candidates(candidates, topic="(loaded)")
        return {
            "report": report.to_dict(),
            "candidates": [c.to_dict() for c in candidates],
            "batch_id": batch_id,
        }
