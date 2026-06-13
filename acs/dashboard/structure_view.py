"""Structure view — displays structure change history for the dashboard."""

from typing import Dict, List, Optional
from acs.storage.structure_history_store import StructureHistoryStore


class StructureView:
    """Dashboard view for structure change history.

    Args:
        store: StructureHistoryStore instance
    """

    def __init__(self, store: StructureHistoryStore):
        self.store = store

    def get_summary(self) -> dict:
        return self.store.get_stats()

    def get_recent(self, site_id: str, limit: int = 10) -> List[dict]:
        return self.store.get_recent(site_id, limit=limit)

    def get_site_stats(self, site_id: str) -> dict:
        return self.store.get_site_stats(site_id)

    def markdown(self, site_id: str = "") -> str:
        summary = self.get_summary()

        lines = [
            "## Structure Change History",
            "",
            "| Metric | Value |",
            "| ------ | ----- |",
            f"| Total snapshots | {summary.get('total_snapshots', 0)} |",
            f"| Unique sites | {summary.get('unique_sites', 0)} |",
            "| | |",
        ]

        if site_id:
            recent = self.get_recent(site_id, limit=10)
            ss = self.get_site_stats(site_id)
            lines.append(f"| Avg change score | {ss.get('avg_change_score', 0):.4f} |")
            lines.append("")

            if recent:
                lines.append("### Recent Snapshots")
                lines.append("| When | URL | Nodes | Change Score |")
                lines.append("| ---- | --- | ----- | ------------ |")
                for r in recent[:10]:
                    url_short = (r.get('url', ''))[:40]
                    lines.append(
                        f"| {r.get('captured_at', '')[:16]} | {url_short} | "
                        f"{r.get('dom_node_count', 0)} | {r.get('change_score', 0):.3f} |"
                    )
                lines.append("")
        else:
            lines.append("")

        return "\n".join(lines)
