"""SourceDiscovery — orchestrate the full discovery → filter → rank → store pipeline."""
from typing import List
from .query_builder import QueryBuilder
from .mock_search_provider import MockSearchProvider
from .compliance_filter import ComplianceFilter
from .relevance_ranker import RelevanceRanker
from .candidate_store import CandidateStore
from .discovery_report import DiscoveryReport


class SourceDiscovery:
    """Main orchestrator: query → search → filter → rank → store → report."""

    def __init__(self, store_dir: str = "acs_data/discovery"):
        self.query_builder = QueryBuilder()
        self.search_provider = MockSearchProvider()
        self.compliance_filter = ComplianceFilter()
        self.relevance_ranker = RelevanceRanker()
        self.store = CandidateStore(store_dir)

    def discover(self, topic: str, keywords: List[str],
                 source_type: str = "webpage",
                 limit: int = 50,
                 auto_select_allowed: bool = False) -> dict:
        """Run full discovery pipeline.

        Args:
            topic: User topic
            keywords: List of keywords
            source_type: webpage / pdf / article / etc.
            limit: Max candidates to return
            auto_select_allowed: If True, auto-select all allowed candidates

        Returns:
            dict with keys: report, candidates, selected_urls_path, store_path
        """
        # 1. Build queries
        queries = self.query_builder.build(topic, keywords, source_type, limit)

        # 2. Mock search
        candidates = self.search_provider.search_all(queries, limit=limit)

        # 3. Compliance filter
        candidates = self.compliance_filter.filter_all(candidates)

        # 4. Relevance ranking
        candidates = self.relevance_ranker.rank(candidates, topic, keywords)

        # 5. Auto-select allowed (if requested)
        if auto_select_allowed:
            for c in candidates:
                if c.compliance_status == "allowed":
                    c.selected = True

        # 6. Build report
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
