"""Multi-site configuration."""
from dataclasses import dataclass, field, asdict
from typing import List, Optional

@dataclass
class SiteConfig:
    site_id: str = ""
    site_name: str = ""
    base_url: str = ""
    enabled: bool = True
    crawl_mode: str = "standard"
    rate_limit_rps: float = 1.0
    allowed_domains: List[str] = field(default_factory=list)
    shadow_enabled: bool = True
    ai_parser_enabled: bool = False
    review_required: bool = True
    notes: str = ""

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict):
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def validate(self) -> List[str]:
        errors = []
        if not self.site_id: errors.append("site_id is required")
        if not self.site_name: errors.append("site_name is required")
        if self.enabled and not self.base_url: errors.append("base_url required for enabled site")
        if self.enabled and not self.allowed_domains: errors.append("allowed_domains required for enabled site")
        if self.rate_limit_rps <= 0: errors.append("rate_limit_rps must be positive")
        return errors

DEFAULT_SITES = [
    SiteConfig(
        site_id="example",
        site_name="Example Site",
        base_url="https://example.com",
        enabled=False,
        allowed_domains=["example.com"],
        notes="Default example site (disabled). Configure your own sites.",
    ),
]
