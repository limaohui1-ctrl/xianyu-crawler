"""TopicDiscoveryFlow — full orchestrator for topic-level whole-web discovery.

P0: Uses MockSearchApiProvider when no real API key is configured.
P1+: Uses Bing/Google/SerpApi when API key is set in .env.

Flow:
  TopicQueryPlanner → SearchApiProvider → SearchApiResultMapper
  → ContentTypeDetector → CandidateDeduplicator
  → SourceQualityScorer → TopicCandidateRanker
  → ComplianceFilter → CandidateStore
"""
import time
from dataclasses import dataclass, field, asdict
from typing import List, Optional

from .topic_query_planner import TopicQueryPlanner
from .search_api_provider import SearchApiProvider, MockSearchApiProvider, SearchApiResult
from .search_api_config import get_search_api_config
from .candidate_url import CandidateUrl
from .content_type_detector import detect_content_type, classify_candidates
from .candidate_deduplicator import dedup_candidates
from .topic_candidate_ranker import rank_topic_candidates
from .source_quality_scorer import score_source_quality
from .compliance_filter import ComplianceFilter
from .url_safety_checker import UrlSafetyChecker
from .search_api_provider_registry import get_search_registry


@dataclass
class TopicDiscoveryReport:
    batch_id: str = ""
    topic: str = ""
    keywords: List[str] = field(default_factory=list)
    queries_generated: int = 0
    raw_results: int = 0
    after_dedup: int = 0
    after_filter: int = 0
    allowed: int = 0
    needs_review: int = 0
    blocked: int = 0
    created_at: str = ""
    candidates: List[dict] = field(default_factory=list)


def _map_result_to_candidate(r: SearchApiResult, query: str) -> dict:
    """Map a SearchApiResult to a CandidateUrl dict."""
    c = CandidateUrl(
        url=r.url,
        title=r.title,
        snippet=r.snippet,
        source_domain=r.source_domain,
        source_type="webpage",
        discovery_method="search_api",
        matched_keywords=[query],
        estimated_relevance=0.7,
        compliance_status="allowed",
        risk_level="low",
        reason=f"search_api query: {query}",
    )
    d = c.to_dict()
    d["query"] = query
    d["content_type"] = detect_content_type(r.url, r.title, r.snippet)
    d["source_quality_score"] = score_source_quality(r.source_domain)
    return d


def discover_by_topic(
    topic: str,
    keywords: List[str] = None,
    content_type: str = "",
    limit: int = 100,
    provider: str = "mock",
    prefer_gov_edu: bool = True,
    max_per_domain: int = 10,
    store_dir: str = "acs_data/discovery",
    enable_compliance: bool = True,
) -> TopicDiscoveryReport:
    """Full topic-level discovery pipeline.

    Args:
        topic: Main topic
        keywords: Keywords list
        content_type: Target content type
        limit: Max candidates after all filtering
        provider: "mock" | "bing" | "google" | "serpapi"
        prefer_gov_edu: Boost gov/edu/org sources
        max_per_domain: Max candidates per domain
        store_dir: Candidate store directory
        enable_compliance: Run ComplianceFilter

    Returns:
        TopicDiscoveryReport with ranked, filtered candidates
    """
    keywords = keywords or []
    batch_id = f"topic_{int(time.time())}"

    # 1. Generate queries
    planner = TopicQueryPlanner()
    queries = planner.plan(topic, keywords, content_type, limit=min(limit // 3, 15))
    if not queries:
        return TopicDiscoveryReport(batch_id=batch_id, topic=topic, keywords=keywords)

    # 2. Search API — auto-detect real API if available
    # Priority: explicit 'auto' > ACS_SEARCH_API_PROVIDER env > 'mock'
    registry = get_search_registry()
    api_source = "mock"

    if provider == "mock" or not registry.is_real_configured:
        api = MockSearchApiProvider()
    else:
        client = registry.get_client(provider)
        if client.available:
            api = client
            api_source = registry.active_provider
        else:
            api = MockSearchApiProvider()
            api_source = f"mock (API unavailable: {client.last_error})"

    # Collect results per query
    all_results = []
    per_query = max(5, limit // max(len(queries), 1))
    for q in queries:
        try:
            results = api.search(q, limit=per_query)
        except Exception:
            continue
        for r in results:
            all_results.append(_map_result_to_candidate(r, q))
        if len(all_results) >= limit * 3:
            break

    if not all_results:
        return TopicDiscoveryReport(
            batch_id=batch_id, topic=topic, keywords=keywords,
            queries_generated=len(queries), raw_results=0,
        )

    raw_count = len(all_results)

    # 3. Dedup
    all_results = dedup_candidates(all_results, max_per_domain=max_per_domain)
    dedup_count = len(all_results)

    # 4. Content type classification
    classify_candidates(all_results)

    # 5. Compliance filter
    if enable_compliance:
        cf = ComplianceFilter()
        checker = UrlSafetyChecker()
        for c in all_results:
            obj = CandidateUrl.from_dict(c)
            cf.evaluate(obj)
            c.update(obj.to_dict())
            # Also run safety check
            safe_ok, safe_reason = checker.check(c.get("url", ""))
            if not safe_ok:
                c["compliance_status"] = "blocked"
                c["risk_level"] = "high"
                c["reason"] = safe_reason or "URL safety check failed"

    # 6. Rank
    all_results = rank_topic_candidates(
        all_results, topic=topic, keywords=keywords,
        content_type=content_type, prefer_gov_edu=prefer_gov_edu,
    )

    # 7. Summarize
    allowed = sum(1 for c in all_results if c.get("compliance_status") == "allowed")
    review = sum(1 for c in all_results if c.get("compliance_status") == "needs_review")
    blocked = sum(1 for c in all_results if c.get("compliance_status") == "blocked")

    # Auto-select allowed only
    for c in all_results:
        if c.get("compliance_status") == "allowed":
            c["selected"] = True

    return TopicDiscoveryReport(
        batch_id=batch_id,
        topic=topic,
        keywords=keywords,
        queries_generated=len(queries),
        raw_results=raw_count,
        after_dedup=dedup_count,
        after_filter=len(all_results),
        allowed=allowed,
        needs_review=review,
        blocked=blocked,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        candidates=all_results[:limit],
    )
