"""
Repair planner — orchestrates failure analysis and generates repair plans.

Combines output from:
  - FailureAnalyzer (failure classification)
  - StructureDiffer (DOM change detection)
  - SelectorRepairer (candidate selectors)
  - AIParser (AI-extracted field hints)

Generates a unified RepairPlan — always with status="pending_review".
The plan is a suggestion, NOT an automated action.

Usage:
    from acs.self_healing.repair_planner import RepairPlanner

    planner = RepairPlanner()
    plan = planner.plan_repair(
        url="...",
        html=current_html,
        failure_report=failure_report,
        structure_diff=structure_diff,
        field_candidates=field_candidates,
    )
    print(plan.to_dict())
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum
import time


class RepairType(str, Enum):
    """Types of repair actions."""
    SELECTOR_REPAIR = "selector_repair"       # Replace failed selectors
    AI_FALLBACK = "ai_fallback"               # Use AI parser as backup
    RETRY_ONLY = "retry_only"                 # Retry with same config
    NO_ACTION = "no_action"                   # Nothing to repair
    TEMPLATE_UPDATE = "template_update"       # Update site template
    INVESTIGATE = "investigate"               # Needs manual investigation


class RepairPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class RepairAction:
    """A single repair action in the plan."""
    action: str = ""                    # Human-readable description
    type: RepairType = RepairType.NO_ACTION
    priority: RepairPriority = RepairPriority.LOW
    auto_applicable: bool = False       # Can be auto-applied? (Phase 4: always False)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "type": self.type.value,
            "priority": self.priority.value,
            "auto_applicable": self.auto_applicable,
        }


@dataclass
class RepairPlan:
    """Complete repair plan for a site/page."""

    url: str = ""
    site_id: str = ""
    repair_needed: bool = False
    repair_type: RepairType = RepairType.NO_ACTION
    priority: RepairPriority = RepairPriority.LOW
    actions: List[RepairAction] = field(default_factory=list)
    field_candidates: List[dict] = field(default_factory=list)
    ai_parser_recommended: bool = False
    status: str = "pending_review"      # ALWAYS pending_review
    generated_at: str = ""
    notes: List[str] = field(default_factory=list)
    switch_to_on_mode_recommended: bool = False
    switch_to_on_mode_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "site_id": self.site_id,
            "repair_needed": self.repair_needed,
            "repair_type": self.repair_type.value,
            "priority": self.priority.value,
            "actions": [a.to_dict() for a in self.actions],
            "field_candidates": self.field_candidates,
            "ai_parser_recommended": self.ai_parser_recommended,
            "status": self.status,
            "generated_at": self.generated_at,
            "notes": self.notes,
            "switch_to_on_mode_recommended": self.switch_to_on_mode_recommended,
            "switch_to_on_mode_reason": self.switch_to_on_mode_reason,
        }


class RepairPlanner:
    """Orchestrates failure analysis results into a repair plan.

    ALWAYS generates plans with status="pending_review".
    NEVER auto-applies fixes.
    """

    def __init__(self):
        pass

    # ── Main planning ────────────────────────────────────────────

    def plan_repair(
        self,
        url: str = "",
        site_id: str = "",
        html: str = "",
        failure_report=None,
        structure_diff=None,
        field_candidates: Optional[List[dict]] = None,
        ai_parse_success: bool = False,
        shadow_stats: Optional[dict] = None,
    ) -> RepairPlan:
        """Generate a comprehensive repair plan.

        Args:
            url: Page URL
            site_id: Site identifier
            html: Current page HTML
            failure_report: FailureReport from FailureAnalyzer
            structure_diff: StructureDiffResult from StructureDiffer
            field_candidates: [FieldRepairResult.to_dict(), ...] from SelectorRepairer
            ai_parse_success: Whether AI parser successfully extracted fields
            shadow_stats: Shadow comparison stats for on-mode assessment

        Returns:
            RepairPlan — always status="pending_review"
        """
        plan = RepairPlan(
            url=url,
            site_id=site_id,
            generated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        )

        actions = []
        notes = []

        # ── 1. Assess failure severity ──
        if failure_report:
            plan.repair_needed = True
            plan.priority = self._map_severity(
                getattr(failure_report, 'severity', 'low') if hasattr(failure_report, 'severity') else 'low'
            )

            # Map failure type to repair type
            ft = getattr(failure_report, 'failure_type', '') if hasattr(failure_report, 'failure_type') else ''
            ft_str = str(ft)

            if "selector" in ft_str.lower() or "missing" in ft_str.lower():
                plan.repair_type = RepairType.SELECTOR_REPAIR
            elif "structure" in ft_str.lower():
                plan.repair_type = RepairType.SELECTOR_REPAIR
            elif "ai_parser" in ft_str.lower():
                plan.repair_type = RepairType.INVESTIGATE
            elif "low_quality" in ft_str.lower():
                plan.repair_type = RepairType.AI_FALLBACK
            elif "http" in ft_str.lower() or "request" in ft_str.lower():
                plan.repair_type = RepairType.RETRY_ONLY
            else:
                plan.repair_type = RepairType.INVESTIGATE

        # ── 2. Structure change → selector repair ──
        if structure_diff and getattr(structure_diff, 'structure_changed', False):
            if not plan.repair_needed:
                plan.repair_needed = True
                plan.repair_type = RepairType.SELECTOR_REPAIR
                plan.priority = RepairPriority.HIGH

            actions.append(RepairAction(
                action=f"Structure change detected (score={getattr(structure_diff, 'change_score', 0):.2f}). Review selectors.",
                type=RepairType.SELECTOR_REPAIR,
                priority=RepairPriority.HIGH,
            ))

            if getattr(structure_diff, 'failed_selectors', []):
                actions.append(RepairAction(
                    action=f"Failed selectors: {', '.join(structure_diff.failed_selectors[:5])}",
                    type=RepairType.SELECTOR_REPAIR,
                    priority=RepairPriority.HIGH,
                ))

        # ── 3. Field repair candidates ──
        if field_candidates:
            plan.field_candidates = field_candidates
            candidate_count = sum(
                len(c.get("candidate_selectors", [])) for c in field_candidates
            )
            if candidate_count > 0:
                actions.append(RepairAction(
                    action=f"Review {candidate_count} selector candidates across {len(field_candidates)} fields",
                    type=RepairType.SELECTOR_REPAIR,
                    priority=PlanPriority.MEDIUM,
                ))

        # ── 4. AI parser recommendation ──
        if failure_report:
            if hasattr(failure_report, 'recommend_ai_parser') and failure_report.recommend_ai_parser:
                plan.ai_parser_recommended = True
                actions.append(RepairAction(
                    action="Enable AI parser as fallback for this site",
                    type=RepairType.AI_FALLBACK,
                    priority=PlanPriority.MEDIUM,
                ))

        if ai_parse_success:
            notes.append("AI parser successfully extracted fields — review AI output quality")
            actions.append(RepairAction(
                action="Verify AI parser output quality before accepting",
                type=RepairType.INVESTIGATE,
                priority=PlanPriority.LOW,
            ))

        # ── 5. On-mode assessment — ALWAYS conservative ──
        plan.switch_to_on_mode_recommended = False
        if shadow_stats:
            total = shadow_stats.get("total_compared", 0)
            sup = shadow_stats.get("superior", 0)
            inf = shadow_stats.get("inferior", 0)
            success_rate = getattr(failure_report, 'reason', '') if failure_report else ''

            if total >= 100 and sup > inf * 2 and not plan.repair_needed:
                plan.switch_to_on_mode_recommended = False  # Still don't auto-switch
                notes.append(
                    f"ACS shadow metrics good (superior={sup}, inferior={inf}), "
                    "but manual review still required before switching to on mode"
                )

        if not plan.switch_to_on_mode_recommended:
            plan.switch_to_on_mode_reason = (
                "Manual review required — do NOT auto-switch to ACS_MODE=on"
            )

        # ── 6. Compile ──
        if not actions and not plan.repair_needed:
            plan.repair_type = RepairType.NO_ACTION
            actions.append(RepairAction(
                action="No repair needed — monitoring only",
                type=RepairType.NO_ACTION,
                priority=PlanPriority.LOW,
            ))

        plan.actions = actions
        plan.notes = notes

        # ALWAYS pending_review
        plan.status = "pending_review"

        return plan

    # ── Quick plan from shadow log ───────────────────────────────

    def plan_from_shadow(
        self,
        url: str = "",
        site_id: str = "",
        shadow_entry: Optional[dict] = None,
    ) -> RepairPlan:
        """Generate a repair plan from a single shadow log entry."""
        if not shadow_entry:
            return RepairPlan(
                url=url, site_id=site_id,
                repair_needed=False,
                repair_type=RepairType.NO_ACTION,
                status="pending_review",
                generated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            )

        acs_success = shadow_entry.get("acs_success", False)
        acs_quality = shadow_entry.get("acs_quality", "unknown")
        acs_completeness = shadow_entry.get("acs_completeness", 0)
        acs_error = shadow_entry.get("acs_error", "")

        plan = RepairPlan(
            url=url,
            site_id=site_id,
            generated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        )

        if not acs_success or acs_completeness < 30:
            plan.repair_needed = True
            plan.repair_type = RepairType.INVESTIGATE
            plan.priority = RepairPriority.MEDIUM if acs_completeness < 20 else RepairPriority.LOW
            plan.actions = [RepairAction(
                action=f"Shadow parse {('failed' if not acs_success else 'low quality')} "
                       f"(completeness={acs_completeness}%). "
                       f"Investigate {'error: ' + acs_error[:80] if acs_error else 'parser performance'}.",
                type=RepairType.INVESTIGATE,
                priority=plan.priority,
            )]

        return plan

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _map_severity(severity) -> RepairPriority:
        s = str(severity).lower()
        if s in ("fatal", "critical"):
            return RepairPriority.CRITICAL
        if s == "high":
            return RepairPriority.HIGH
        if s == "medium":
            return RepairPriority.MEDIUM
        return RepairPriority.LOW


# ── Workaround: PlanPriority for use inside RepairPlanner ────────

class PlanPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
