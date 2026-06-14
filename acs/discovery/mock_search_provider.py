"""MockSearchProvider — returns fake candidate URLs for P0 testing.

P0 uses mock data only — no real search engine, no network calls.
"""
import time
from .candidate_url import CandidateUrl


# ── Mock candidate database ──
_MOCK_CANDIDATES = [
    # government / edu sources — high trust
    CandidateUrl(
        url="https://www.epb.gov.cn/example/vocs-treatment-case-study",
        title="园区VOCs治理典型案例分析",
        snippet="系统介绍工业园区的挥发性有机物治理案例，包含活性炭吸附、催化燃烧等主流技术方案。",
        source_domain="epb.gov.cn",
        source_type="webpage",
        discovery_method="mock",
        matched_keywords=["VOCs", "活性炭", "治理"],
        estimated_relevance=0.92,
        compliance_status="allowed",
        risk_level="low",
    ),
    CandidateUrl(
        url="https://www.mee.gov.cn/example/activated-carbon-guidelines",
        title="活性炭吸附技术在废气治理中的应用指南",
        snippet="中华人民共和国生态环境部发布的活性炭吸附技术应用指南，包含选型、更换周期和处置建议。",
        source_domain="mee.gov.cn",
        source_type="webpage",
        discovery_method="mock",
        matched_keywords=["活性炭", "废气治理"],
        estimated_relevance=0.88,
        compliance_status="allowed",
        risk_level="low",
    ),
    CandidateUrl(
        url="https://sthjj.zhuhai.gov.cn/example/vocs-compliance-report",
        title="挥发性有机物治理整改报告汇编",
        snippet="珠海市生态环境局发布的辖区内企业VOCs治理整改报告汇编，包含活性炭更换记录和检测数据。",
        source_domain="sthjj.zhuhai.gov.cn",
        source_type="webpage",
        discovery_method="mock",
        matched_keywords=["VOCs", "整改报告"],
        estimated_relevance=0.85,
        compliance_status="allowed",
        risk_level="low",
    ),
    CandidateUrl(
        url="https://www.zhbb.gov.cn/example/industrial-waste-gas-treatment",
        title="工业园区废气治理技术指南",
        snippet="中国环保部发布的工业废气治理技术指南，重点分析活性炭吸附法和生物处理法的适用场景。",
        source_domain="zhbb.gov.cn",
        source_type="pdf",
        discovery_method="mock",
        matched_keywords=["废气治理", "活性炭"],
        estimated_relevance=0.82,
        compliance_status="allowed",
        risk_level="low",
    ),
    CandidateUrl(
        url="https://www.chinaenvironment.org/reports/vocs-treatment-2025",
        title="2025年度VOCs治理行业发展报告",
        snippet="非营利组织发布的中国VOCs治理行业年度报告，涵盖政策、技术和市场分析。",
        source_domain="chinaenvironment.org",
        source_type="webpage",
        discovery_method="mock",
        matched_keywords=["VOCs", "治理"],
        estimated_relevance=0.78,
        compliance_status="allowed",
        risk_level="low",
    ),

    # Commercial / semi-commercial — needs review  
    CandidateUrl(
        url="https://example.com/environmental/vocs-supplier-list",
        title="XXX环保设备供应商产品目录",
        snippet="提供活性炭吸附设备、催化燃烧设备的供应商产品目录和技术参数。",
        source_domain="example.com",
        source_type="webpage",
        discovery_method="mock",
        matched_keywords=["活性炭", "设备"],
        estimated_relevance=0.71,
        compliance_status="needs_review",
        risk_level="medium",
    ),
    CandidateUrl(
        url="https://xxx.co/whitepapers/vocs-treatment-solution.pdf",
        title="XXX公司VOCs治理解决方案.pdf",
        snippet="某环保公司发布的白皮书，介绍其VOCs治理专利技术和成功案例（含商业内容）。",
        source_domain="xxx.co",
        source_type="pdf",
        discovery_method="mock",
        matched_keywords=["VOCs", "治理"],
        estimated_relevance=0.65,
        compliance_status="needs_review",
        risk_level="high",
    ),
    CandidateUrl(
        url="https://envtech.com/blog/activated-carbon-replacement-guide",
        title="活性炭更换周期与成本对比指南",
        snippet="技术博客，讨论不同工况下活性炭的更换频率和成本对比。来源为商业公司博客。",
        source_domain="envtech.com",
        source_type="webpage",
        discovery_method="mock",
        matched_keywords=["活性炭"],
        estimated_relevance=0.60,
        compliance_status="needs_review",
        risk_level="medium",
    ),

    # BLOCKED — commercial platform / paywall
    CandidateUrl(
        url="https://www.amazon.com/dp/B0EXAMPLE",
        title="活性炭滤芯 - 工业级废气处理",
        snippet="Amazon product listing for industrial activated carbon filter.",
        source_domain="amazon.com",
        source_type="webpage",
        discovery_method="mock",
        matched_keywords=["活性炭"],
        estimated_relevance=0.45,
        compliance_status="blocked",
        risk_level="blocked",
        reason="commercial platform with confirmed 403 blocking",
    ),
    CandidateUrl(
        url="https://www.walmart.com/search?q=activated+carbon+filter",
        title="Activated Carbon Filter - Walmart.com",
        snippet="Walmart search results for activated carbon filters.",
        source_domain="walmart.com",
        source_type="webpage",
        discovery_method="mock",
        matched_keywords=["活性炭"],
        estimated_relevance=0.30,
        compliance_status="blocked",
        risk_level="blocked",
    ),
    CandidateUrl(
        url="https://paywall.cn/reports/vocs-governance-full.pdf",
        title="付费资料平台 - VOCs 治理专题研究报告",
        snippet="需要订阅或单次付费才能下载的VOCs治理专题研究报告全文。",
        source_domain="paywall.cn",
        source_type="pdf",
        discovery_method="mock",
        matched_keywords=["VOCs", "治理"],
        estimated_relevance=0.40,
        compliance_status="blocked",
        risk_level="blocked",
        reason="paywall page",
    ),
    CandidateUrl(
        url="https://premium-research.com/login?return=/report/vocs",
        title="VOCs治理市场研究报告（需要登录）",
        snippet="需要注册账号并登录才能访问的付费研究报告。",
        source_domain="premium-research.com",
        source_type="webpage",
        discovery_method="mock",
        matched_keywords=["VOCs"],
        estimated_relevance=0.35,
        compliance_status="blocked",
        risk_level="blocked",
        reason="login page",
    ),
]


class MockSearchProvider:
    """Mock search provider for P0 testing. Returns predefined candidates."""

    def __init__(self):
        self._candidates = _MOCK_CANDIDATES

    def search(self, query: str, limit: int = 20) -> list:
        """Return mock candidates matching the query.

        In P0, relevance is pre-computed. Matching is done by simple
        keyword overlap with the query.
        """
        query_lower = query.lower()
        matched = []
        for c in self._candidates:
            # Simple keyword match check
            title = c.title.lower()
            snippet = c.snippet.lower()
            keywords = " ".join(c.matched_keywords).lower()
            if (any(q in title for q in query_lower.split()) or
                any(q in snippet for q in query_lower.split()) or
                any(q in keywords for q in query_lower.split())):
                matched.append(c)

        # Deduplicate
        seen = set()
        unique = []
        for c in matched:
            if c.url not in seen:
                seen.add(c.url)
                unique.append(c)

        return unique[:limit]

    def search_all(self, queries: list, limit: int = 50) -> list:
        """Search across multiple queries, merge and deduplicate results."""
        all_results = []
        seen = set()
        for q in queries:
            results = self.search(q, limit=limit)
            for c in results:
                if c.url not in seen:
                    seen.add(c.url)
                    all_results.append(c)
        return all_results[:limit]
