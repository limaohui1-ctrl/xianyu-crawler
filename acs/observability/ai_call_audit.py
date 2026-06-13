"""
AI Call Audit — JSONL audit log of every AI provider call.

Records every call with tokens, cost, timing, and status.
NEVER records API keys, cookies, or sensitive tokens.

Usage:
    from acs.observability.ai_call_audit import AICallAuditor

    auditor = AICallAuditor("logs/ai_call_audit.jsonl")
    auditor.log_call(
        call_id="run_001",
        url="https://example.com/page",
        tokens_prompt=500,
        tokens_completion=200,
        success=True,
    )
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import json
import os
import threading
import time


@dataclass
class AICallRecord:
    """A single AI call record — safe for logging."""
    call_id: str = ""
    timestamp: str = ""
    url: str = ""
    model: str = ""
    provider: str = ""
    tokens_prompt: int = 0
    tokens_completion: int = 0
    estimated_cost: float = 0.0
    success: bool = False
    error: str = ""
    elapsed_seconds: float = 0.0
    parser: str = "ai_parser"
    # Deliberately NO api_key, NO cookies, NO full prompt

    def to_dict(self) -> dict:
        return {
            "call_id": self.call_id,
            "timestamp": self.timestamp,
            "url": self.url,
            "model": self.model,
            "provider": self.provider,
            "tokens_prompt": self.tokens_prompt,
            "tokens_completion": self.tokens_completion,
            "estimated_cost": round(self.estimated_cost, 6),
            "success": self.success,
            "error": self.error,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "parser": self.parser,
        }


class AICallAuditor:
    """Thread-safe JSONL audit log for AI calls.

    Args:
        log_path: Path to JSONL log file
        auto_flush: Flush after every write (slower but safer)
    """

    def __init__(self, log_path: str = "logs/ai_call_audit.jsonl",
                 auto_flush: bool = True):
        self.log_path = log_path
        self.auto_flush = auto_flush
        self._lock = threading.Lock()
        self._total_calls: int = 0
        self._ensure_dir()

    def _ensure_dir(self):
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)

    def log_call(
        self,
        call_id: str = "",
        url: str = "",
        model: str = "",
        provider: str = "openai_compatible",
        tokens_prompt: int = 0,
        tokens_completion: int = 0,
        estimated_cost: float = 0.0,
        success: bool = False,
        error: str = "",
        elapsed_seconds: float = 0.0,
    ) -> AICallRecord:
        """Log a single AI call. Returns the record."""
        record = AICallRecord(
            call_id=call_id or f"ai_{int(time.time() * 1000)}",
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            url=url[:500],
            model=model,
            provider=provider,
            tokens_prompt=tokens_prompt,
            tokens_completion=tokens_completion,
            estimated_cost=estimated_cost,
            success=success,
            error=str(error)[:500],
            elapsed_seconds=elapsed_seconds,
        )
        with self._lock:
            try:
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
                    if self.auto_flush:
                        f.flush()
                self._total_calls += 1
            except OSError as e:
                pass  # Log failure shouldn't crash the caller
        return record

    def log_call_from_response(self, call_id: str, url: str, model: str,
                               response, elapsed: float = 0.0) -> AICallRecord:
        """Log from an AIResponse object."""
        tokens = getattr(response, 'tokens', {}) if hasattr(response, 'tokens') else {}
        return self.log_call(
            call_id=call_id,
            url=url,
            model=model,
            tokens_prompt=tokens.get("prompt", 0),
            tokens_completion=tokens.get("completion", 0),
            success=not bool(getattr(response, 'error', '')),
            error=getattr(response, 'error', ''),
            elapsed_seconds=elapsed,
        )

    def read_logs(self, limit: int = 100) -> List[dict]:
        """Read recent log entries."""
        entries = []
        if not os.path.exists(self.log_path):
            return entries
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                for line in lines[-limit:]:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except OSError:
            pass
        return entries

    def get_stats(self) -> dict:
        """Aggregate stats from audit log."""
        entries = self.read_logs(limit=10000)
        total = len(entries)
        successes = sum(1 for e in entries if e.get("success"))
        total_tokens = sum(e.get("tokens_prompt", 0) + e.get("tokens_completion", 0)
                          for e in entries)
        total_cost = sum(e.get("estimated_cost", 0) for e in entries)
        errors = total - successes
        return {
            "total_calls": total,
            "successful_calls": successes,
            "failed_calls": errors,
            "total_tokens": total_tokens,
            "estimated_cost": round(total_cost, 6),
            "log_path": self.log_path,
        }

    @property
    def call_count(self) -> int:
        return self._total_calls
