"""
JSON export — export ParseResults to structured JSON formats.

Supports three export formats:
  1. Full JSON (record_dict format, one object per result)
  2. Newline-delimited JSON (JSONL, one line per result)
  3. Summary JSON (aggregate stats + results array)

Also supports:
  - File rotation (by count)
  - Encoding control
  - Pretty vs compact output
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import json
import os
import time

from acs.core.result_model import ParseResult


@dataclass
class ExportConfig:
    """Configuration for JSON export."""
    output_dir: str = "exports"
    format: str = "json"           # json | jsonl | summary
    pretty: bool = True            # Pretty-print (indent=2)
    encoding: str = "utf-8"
    max_per_file: int = 0          # 0 = no splitting
    include_metadata: bool = True   # Include parser metadata in output
    include_raw: bool = False       # Include raw_html/raw_json (large!)
    fields: Optional[List[str]] = None  # Which fields to include (None = all)


class JsonExporter:
    """Export ParseResults to JSON in various formats.

    Usage:
        exporter = JsonExporter(ExportConfig(output_dir="./exports"))
        exporter.export(results, filename="crawl_20240613")
    """

    def __init__(self, config: Optional[ExportConfig] = None):
        self.config = config or ExportConfig()

    # ── Main export ──

    def export(self, results: List[ParseResult], filename: str = "",
               part: int = 0) -> str:
        """Export results to a JSON file.

        Args:
            results: List of ParseResult objects
            filename: Base name for the output file (without extension)
            part: Part number for multi-file exports

        Returns:
            Absolute path to the exported file
        """
        if not filename:
            filename = f"export_{time.strftime('%Y%m%d_%H%M%S')}"

        os.makedirs(self.config.output_dir, exist_ok=True)

        if self.config.format == "jsonl":
            return self._export_jsonl(results, filename, part)
        elif self.config.format == "summary":
            return self._export_summary(results, filename)
        else:
            return self._export_json(results, filename, part)

    def export_batch(self, results: List[ParseResult], filename: str = "") -> List[str]:
        """Export results, splitting into multiple files if max_per_file is set.

        Returns list of output file paths.
        """
        max_per = self.config.max_per_file
        if max_per <= 0 or len(results) <= max_per:
            path = self.export(results, filename)
            return [path]

        paths = []
        for i in range(0, len(results), max_per):
            chunk = results[i:i + max_per]
            path = self.export(chunk, filename, part=i // max_per + 1)
            paths.append(path)
        return paths

    # ── JSON (single file) ──

    def _export_json(self, results: List[ParseResult], filename: str, part: int = 0) -> str:
        """Export as a single JSON array or object."""
        suffix = f"_part{part}" if part > 0 else ""
        filepath = os.path.join(self.config.output_dir, f"{filename}{suffix}.json")

        records = [self._result_to_dict(r) for r in results]

        if self.config.pretty:
            content = json.dumps(records, ensure_ascii=False, indent=2)
        else:
            content = json.dumps(records, ensure_ascii=False)

        with open(filepath, "w", encoding=self.config.encoding) as f:
            f.write(content)

        return os.path.abspath(filepath)

    # ── JSONL (newline-delimited) ──

    def _export_jsonl(self, results: List[ParseResult], filename: str, part: int = 0) -> str:
        """Export as newline-delimited JSON (one JSON object per line)."""
        suffix = f"_part{part}" if part > 0 else ""
        filepath = os.path.join(self.config.output_dir, f"{filename}{suffix}.jsonl")

        with open(filepath, "w", encoding=self.config.encoding) as f:
            for result in results:
                record = self._result_to_dict(result)
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        return os.path.abspath(filepath)

    # ── Summary ──

    def _export_summary(self, results: List[ParseResult], filename: str) -> str:
        """Export as a summary report with stats."""
        filepath = os.path.join(self.config.output_dir, f"{filename}_summary.json")

        records = [self._result_to_dict(r) for r in results]

        # Compute summary
        total = len(results)
        high_quality = sum(1 for r in results if r.quality_label == "high")
        medium_quality = sum(1 for r in results if r.quality_label == "medium")
        low_quality = sum(1 for r in results if r.quality_label == "low")
        with_errors = sum(1 for r in results if r.error)
        avg_completeness = (
            round(sum(r.completeness for r in results) / max(total, 1), 1)
            if total > 0 else 0
        )

        # Group by domain
        domains: Dict[str, int] = {}
        for r in results:
            domains[r.domain] = domains.get(r.domain, 0) + 1

        output = {
            "export_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "summary": {
                "total_results": total,
                "high_quality": high_quality,
                "medium_quality": medium_quality,
                "low_quality": low_quality,
                "with_errors": with_errors,
                "avg_completeness": avg_completeness,
                "domains": dict(sorted(domains.items(), key=lambda x: -x[1])[:30]),
            },
            "results": records,
        }

        with open(filepath, "w", encoding=self.config.encoding) as f:
            json.dump(output, f, ensure_ascii=False, indent=2 if self.config.pretty else None)

        return os.path.abspath(filepath)

    # ── Helpers ──

    def _result_to_dict(self, result: ParseResult) -> dict:
        """Convert a ParseResult to an exportable dict."""
        if self.config.fields:
            full = result.to_dict()
            return {k: full.get(k) for k in self.config.fields if k in full}

        d = result.to_record_dict()

        if self.config.include_metadata:
            d["_parser"] = result.parser_used
            d["_fetch_quality"] = result.fetch_quality
            d["_quality_label"] = result.quality_label

        if self.config.include_raw:
            d["_raw_html"] = result.raw_html[:5000] if result.raw_html else ""

        return d

    # ── Static convenience ──

    @staticmethod
    def export_to_json(results: List[ParseResult], filepath: str,
                       pretty: bool = True) -> str:
        """Quick one-shot export."""
        dirpath = os.path.dirname(os.path.abspath(filepath))
        os.makedirs(dirpath, exist_ok=True)
        records = [r.to_record_dict() for r in results]
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2 if pretty else None)
        return os.path.abspath(filepath)

    @staticmethod
    def export_to_jsonl(results: List[ParseResult], filepath: str) -> str:
        """Quick one-shot JSONL export."""
        dirpath = os.path.dirname(os.path.abspath(filepath))
        os.makedirs(dirpath, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r.to_record_dict(), ensure_ascii=False) + "\n")
        return os.path.abspath(filepath)
