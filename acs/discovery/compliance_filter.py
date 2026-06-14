"""ComplianceFilter — evaluate whether a candidate URL can be collected."""
import re


# Known commercial platforms with confirmed anti-scraping protection
BLOCKED_DOMAINS = {
    "amazon.com": "commercial platform with confirmed 403 blocking",
    "amazon.ca": "commercial platform with confirmed 403 blocking",
    "walmart.com": "commercial platform with confirmed 403 blocking",
    "bestbuy.com": "commercial platform with confirmed 403 blocking",
    "bestbuy.ca": "commercial platform with confirmed 403 blocking",
    "homedepot.com": "commercial platform with confirmed 403 blocking",
    "homedepot.ca": "commercial platform with confirmed 403 blocking",
    "ebay.com": "commercial platform with confirmed 403 blocking",
    "target.com": "commercial platform with confirmed 403 blocking",
    "costco.com": "commercial platform with confirmed 403 blocking",
    "etsy.com": "commercial platform with confirmed 403 blocking",
}

# URL patterns that indicate authentication / paywall / access control
BLOCKED_PATTERNS = [
    (r"/login", "login page"),
    (r"/signin", "sign-in page"),
    (r"/auth", "authentication required"),
    (r"/account", "account-gated content"),
    (r"token=", "URL contains token parameter"),
    (r"session=", "URL contains session parameter"),
    (r"cookie=", "URL contains cookie parameter"),
    (r"captcha", "captcha-gated page"),
    (r"/paywall", "paywall page"),
    (r"/subscribe", "subscription-gated page"),
    (r"/checkout", "checkout page (not content)"),
    (r"/cart", "shopping cart page (not content)"),
]

# Trusted domains (gov, edu, org etc.) get a slight boost but still filtered
TRUSTED_DOMAIN_SUFFIXES = [".gov", ".edu", ".org", ".gov.cn", ".edu.cn"]


class ComplianceFilter:
    """Evaluates candidate URLs against compliance rules. Never bypasses blocks."""

    def evaluate(self, candidate: "CandidateUrl") -> "CandidateUrl":
        """Evaluate one candidate URL. Returns the same object with compliance fields set."""
        from .candidate_url import CandidateUrl

        url = candidate.url.lower()

        # Check blocked domains
        for domain, reason in BLOCKED_DOMAINS.items():
            if domain in url:
                candidate.compliance_status = "blocked"
                candidate.risk_level = "blocked"
                candidate.reason = reason
                return candidate

        # Check blocked patterns
        for pattern, reason in BLOCKED_PATTERNS:
            if re.search(pattern, url):
                candidate.compliance_status = "blocked"
                candidate.risk_level = "blocked"
                candidate.reason = reason
                return candidate

        # Unknown commercial domains → needs_review
        commercial_tlds = [".com", ".net", ".shop", ".store", ".io"]
        if any(candidate.source_domain.endswith(t) for t in commercial_tlds):
            if not any(candidate.source_domain.endswith(t) for t in TRUSTED_DOMAIN_SUFFIXES):
                candidate.compliance_status = "needs_review"
                candidate.risk_level = "medium"
                candidate.reason = "commercial domain, needs manual review"
                return candidate

        # Trusted domains → allowed
        if any(candidate.source_domain.endswith(t) for t in TRUSTED_DOMAIN_SUFFIXES):
            candidate.compliance_status = "allowed"
            candidate.risk_level = "low"
            candidate.reason = ""
            return candidate

        # Local files → allowed
        if candidate.source_type == "local_file":
            candidate.compliance_status = "allowed"
            candidate.risk_level = "low"
            candidate.reason = ""
            return candidate

        # Default: allowed
        candidate.compliance_status = "allowed"
        candidate.risk_level = "low"
        candidate.reason = ""
        return candidate

    def filter_all(self, candidates: list) -> list:
        """Filter all candidates. Returns same list with compliance fields updated."""
        return [self.evaluate(c) for c in candidates]
