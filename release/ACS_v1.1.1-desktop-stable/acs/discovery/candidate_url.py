"""CandidateUrl — discovered source candidate data model."""
from dataclasses import dataclass, field, asdict
from typing import List


@dataclass
class CandidateUrl:
    url: str = ""
    title: str = ""
    snippet: str = ""
    source_domain: str = ""
    source_type: str = "webpage"
    discovery_method: str = "mock"
    matched_keywords: List[str] = field(default_factory=list)
    estimated_relevance: float = 0.0
    compliance_status: str = "allowed"
    risk_level: str = "low"
    reason: str = ""
    selected: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CandidateUrl":
        fields = set(cls.__dataclass_fields__.keys())
        return cls(**{k: v for k, v in d.items() if k in fields})
