"""DiscoveryReport — summary report after source discovery."""
from dataclasses import dataclass, asdict
from typing import List
import time


@dataclass
class DiscoveryReport:
    batch_id: str = ""
    topic: str = ""
    keywords: List[str] = None
    source_type: str = "webpage"
    total_candidates: int = 0
    allowed_count: int = 0
    needs_review_count: int = 0
    blocked_count: int = 0
    selected_count: int = 0
    queries_used: int = 0
    created_at: str = ""

    def __post_init__(self):
        if self.keywords is None:
            self.keywords = []
        if not self.created_at:
            self.created_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        if not self.batch_id:
            self.batch_id = f"discovery_{int(time.time()*1000)}"

    @classmethod
    def from_candidates(cls, candidates: list, topic: str = "",
                        keywords: list = None, source_type: str = "webpage",
                        queries_used: int = 0) -> "DiscoveryReport":
        """Build report from a list of CandidateUrl objects."""
        return cls(
            topic=topic,
            keywords=keywords or [],
            source_type=source_type,
            total_candidates=len(candidates),
            allowed_count=sum(1 for c in candidates if c.compliance_status == "allowed"),
            needs_review_count=sum(1 for c in candidates if c.compliance_status == "needs_review"),
            blocked_count=sum(1 for c in candidates if c.compliance_status == "blocked"),
            selected_count=sum(1 for c in candidates if c.selected),
            queries_used=queries_used,
        )

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> str:
        return (
            f"Discovery '{self.topic}': {self.total_candidates} total "
            f"({self.allowed_count} ok, {self.needs_review_count} review, "
            f"{self.blocked_count} blocked), {self.selected_count} selected"
        )
