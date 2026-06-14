"""CandidateStore — persist discovered candidate URLs to JSON."""
import json
import os
import time
from typing import List


DEFAULT_STORE_DIR = "acs_data/discovery"


class CandidateStore:
    """Persist candidate URLs and export selected URLs to txt."""

    def __init__(self, store_dir: str = DEFAULT_STORE_DIR):
        self.store_dir = store_dir
        os.makedirs(self.store_dir, exist_ok=True)

    def save(self, candidates: List["CandidateUrl"], batch_id: str = "") -> str:
        """Save all candidates for a batch. Returns file path."""
        if not batch_id:
            batch_id = f"batch_{int(time.time()*1000)}"
        path = os.path.join(self.store_dir, f"{batch_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump([c.to_dict() for c in candidates], f, ensure_ascii=False, indent=2)
        return path

    def load(self, batch_id: str) -> list:
        """Load candidates for a batch."""
        path = os.path.join(self.store_dir, f"{batch_id}.json")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        from .candidate_url import CandidateUrl
        return [CandidateUrl.from_dict(d) for d in data]

    def export_selected_urls(self, candidates: List["CandidateUrl"],
                             output_path: str = "") -> str:
        """Export selected (selected=True) URLs to a txt file. Returns file path."""
        if not output_path:
            output_path = os.path.join(self.store_dir, "selected_urls.txt")
        selected = [c.url for c in candidates if c.selected]
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(selected) + "\n")
        return output_path

    def mark_selected(self, candidates: List["CandidateUrl"],
                      urls: List[str]) -> List["CandidateUrl"]:
        """Mark specific URLs as selected."""
        url_set = set(urls)
        for c in candidates:
            if c.url in url_set and c.compliance_status != "blocked":
                c.selected = True
        return candidates

    def get_by_status(self, candidates: List["CandidateUrl"],
                      status: str) -> List["CandidateUrl"]:
        """Filter candidates by compliance_status."""
        return [c for c in candidates if c.compliance_status == status]

    def get_selected(self, candidates: List["CandidateUrl"]) -> List["CandidateUrl"]:
        """Get all selected candidates."""
        return [c for c in candidates if c.selected]
