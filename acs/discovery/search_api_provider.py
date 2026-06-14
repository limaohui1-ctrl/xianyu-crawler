"""SearchApiProvider — abstract interface + mock implementation for search APIs.

P0 provides a MockSearchApiProvider that returns demo results.
Real implementations (Bing, Google, SerpApi) extend this when API keys are configured.
API keys are NEVER in this file — they come from SearchApiConfig (env vars only).
"""
from typing import List
from dataclasses import dataclass, field, asdict
from .candidate_url import CandidateUrl


@dataclass
class SearchApiResult:
    """Raw search result from any search API, before mapping to CandidateUrl."""
    url: str = ""
    title: str = ""
    snippet: str = ""
    source_domain: str = ""
    query: str = ""
    rank: int = 0
    raw_data: dict = field(default_factory=dict)

    def to_dict(self):
        d = asdict(self)
        # Strip raw_data to avoid leaking API response internals
        d.pop("raw_data", None)
        return d


class SearchApiProvider:
    """Abstract base: search via official API. NEVER scrapes HTML."""

    def __init__(self, config=None):
        from .search_api_config import SearchApiConfig
        self.config = config or SearchApiConfig(provider="none")

    def search(self, query: str, limit: int = 20) -> List[SearchApiResult]:
        """Execute a search query. Must be implemented by subclasses."""
        raise NotImplementedError

    def is_available(self) -> bool:
        """Check if this provider is configured and usable."""
        return self.config.enabled and self.config.configured


class MockSearchApiProvider(SearchApiProvider):
    """Mock implementation for P0/testing — returns demo candidate results.

    Used when no real search API key is configured.
    """

    _MOCK_RESULTS = [
        SearchApiResult(
            url="https://www.epb.gov.cn/vocs-treatment-case-2025",
            title="2025年工业园区VOCs治理典型案例汇编",
            snippet="生态环境部发布工业园区挥发性有机物(VOCs)治理典型案例，包含活性炭吸附技术应用、催化燃烧等方案。",
            source_domain="epb.gov.cn", query="", rank=1,
        ),
        SearchApiResult(
            url="https://www.mee.gov.cn/activated-carbon-policy-2024",
            title="活性炭吸附法在废气治理中的技术政策",
            snippet="中华人民共和国生态环境部关于活性炭吸附技术在大气污染防治中的应用指导意见。",
            source_domain="mee.gov.cn", query="", rank=2,
        ),
        SearchApiResult(
            url="https://sthjj.beijing.gov.cn/vocs-rectification-report",
            title="北京市挥发性有机物治理整改报告公示",
            snippet="北京市生态环境局公示辖区内涉VOCs排放企业的治理整改报告。",
            source_domain="sthjj.beijing.gov.cn", query="", rank=3,
        ),
        SearchApiResult(
            url="https://www.chinaenvironment.org/vocs-industry-report",
            title="VOCs治理行业发展年度报告2025",
            snippet="中国环保产业协会发布VOCs治理行业年度报告，涵盖技术、市场与政策分析。",
            source_domain="chinaenvironment.org", query="", rank=4,
        ),
        SearchApiResult(
            url="https://example.edu.cn/environment/air-quality-review",
            title="城市空气质量改善技术综述",
            snippet="国内高校发表的空气质量改善技术综述论文，涉及VOCs排放控制。",
            source_domain="example.edu.cn", query="", rank=5,
        ),
        SearchApiResult(
            url="https://amazon.com/vocs-filter-products",
            title="VOCs Filter Products — Amazon.com",
            snippet="Shop VOCs air filters at Amazon. Free shipping on qualified orders.",
            source_domain="amazon.com", query="", rank=6,
        ),
    ]

    def search(self, query: str, limit: int = 20) -> List[SearchApiResult]:
        """Return mock results filtered to the given limit."""
        results = []
        for r in self._MOCK_RESULTS[:limit]:
            r.query = query
            results.append(r)
        return results

    def is_available(self):
        return True  # Mock is always available
