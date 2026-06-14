"""
Cost report — generates cost summaries from AI call audit data.

Supports JSON and Markdown export.  NEVER includes API keys.

Usage:
    from acs.observability.cost_report import CostReport

    report = CostReport()
    report.record_call(tokens_prompt=500, tokens_completion=200, success=True)
    print(report.markdown_summary())
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import json
import time


@dataclass
class CostEntry:
    """A single cost entry for the report."""
    call_id: str = ""
    timestamp: str = ""
    url: str = ""
    tokens_prompt: int = 0
    tokens_completion: int = 0
    cost: float = 0.0
    success: bool = False
    error: str = ""


@dataclass
class CostSummary:
    """Aggregated cost summary."""
    run_id: str = ""
    total_ai_calls: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    estimated_cost: float = 0.0
    max_cost_per_run: float = 0.0
    cost_limit_reached: bool = False
    ai_calls_blocked_by_policy: int = 0
    failed_ai_calls: int = 0
    generated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "total_ai_calls": self.total_ai_calls,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "estimated_cost": round(self.estimated_cost, 6),
            "max_cost_per_run": round(self.max_cost_per_run, 2),
            "cost_limit_reached": self.cost_limit_reached,
            "ai_calls_blocked_by_policy": self.ai_calls_blocked_by_policy,
            "failed_ai_calls": self.failed_ai_calls,
            "generated_at": self.generated_at,
        }


class CostReport:
    """Tracks and reports AI call costs within a single run.

    Args:
        run_id: Identifier for this run
        max_cost: Maximum allowed cost before blocking
        pricing_prompt_per_1k: Cost per 1000 prompt tokens
        pricing_completion_per_1k: Cost per 1000 completion tokens
    """

    def __init__(
        self,
        run_id: str = "",
        max_cost: float = 1.00,
        pricing_prompt_per_1k: float = 0.001,
        pricing_completion_per_1k: float = 0.002,
    ):
        self.run_id = run_id or f"run_{int(time.time())}"
        self.max_cost = max_cost
        self.prompt_rate = pricing_prompt_per_1k / 1000.0
        self.completion_rate = pricing_completion_per_1k / 1000.0
        self._entries: List[CostEntry] = []
        self._total_cost: float = 0.0
        self._total_prompt: int = 0
        self._total_completion: int = 0
        self._total_calls: int = 0
        self._failed: int = 0
        self._blocked: int = 0
        self._limit_reached: bool = False

    def record_call(
        self,
        call_id: str = "",
        url: str = "",
        tokens_prompt: int = 0,
        tokens_completion: int = 0,
        success: bool = False,
        error: str = "",
    ):
        cost = (tokens_prompt * self.prompt_rate +
                tokens_completion * self.completion_rate)
        self._entries.append(CostEntry(
            call_id=call_id, timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            url=url[:500], tokens_prompt=tokens_prompt,
            tokens_completion=tokens_completion, cost=cost,
            success=success, error=error,
        ))
        self._total_calls += 1
        self._total_prompt += tokens_prompt
        self._total_completion += tokens_completion
        self._total_cost += cost
        if not success:
            self._failed += 1

    def record_blocked(self):
        """Record that an AI call was blocked by policy."""
        self._blocked += 1

    def check_limit(self) -> bool:
        """Check if cost limit has been reached."""
        if self._total_cost >= self.max_cost:
            self._limit_reached = True
        return self._limit_reached

    def get_summary(self) -> CostSummary:
        return CostSummary(
            run_id=self.run_id,
            total_ai_calls=self._total_calls,
            total_prompt_tokens=self._total_prompt,
            total_completion_tokens=self._total_completion,
            estimated_cost=round(self._total_cost, 6),
            max_cost_per_run=self.max_cost,
            cost_limit_reached=self._limit_reached,
            ai_calls_blocked_by_policy=self._blocked,
            failed_ai_calls=self._failed,
            generated_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )

    def to_json(self, indent: int = 2) -> str:
        s = self.get_summary()
        data = s.to_dict()
        data["entries"] = [
            {"call_id": e.call_id, "url": e.url, "cost": round(e.cost, 6),
             "success": e.success, "error": e.error}
            for e in self._entries[-20:]  # Last 20 entries
        ]
        return json.dumps(data, ensure_ascii=False, indent=indent)

    def markdown_summary(self) -> str:
        s = self.get_summary()
        lines = [
            "# AI Cost Report",
            "",
            f"Run ID: `{s.run_id}`",
            f"Generated: {s.generated_at}",
            "",
            "| Metric | Value |",
            "| ------ | ----- |",
            f"| Total AI calls | {s.total_ai_calls} |",
            f"| Prompt tokens | {s.total_prompt_tokens:,} |",
            f"| Completion tokens | {s.total_completion_tokens:,} |",
            f"| **Estimated cost** | **${s.estimated_cost:.6f}** |",
            f"| Max cost per run | ${s.max_cost_per_run:.2f} |",
            f"| Cost limit reached | {'Yes ⚠️' if s.cost_limit_reached else 'No'} |",
            f"| Calls blocked by policy | {s.ai_calls_blocked_by_policy} |",
            f"| Failed AI calls | {s.failed_ai_calls} |",
            "",
            "> ⚠️ No API keys, cookies, or sensitive data are ever logged.",
        ]
        return "\n".join(lines)

    def save_json(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())
