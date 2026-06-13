"""Tests for acs.self_healing.repair_planner — repair plan generation, always pending_review."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from acs.self_healing.repair_planner import RepairPlanner, RepairPlan, RepairType, RepairPriority

class TestRepairPlanner:
    def test_plan_from_failure_report_selector_failed(self):
        class FR: pass
        fr = FR(); fr.failure_type = "selector_failed"; fr.severity = "medium"
        fr.recommend_ai_parser = True; fr.recommend_selector_repair = True; fr.reason = "selector failed"
        planner = RepairPlanner()
        plan = planner.plan_repair(url="http://x.com", failure_report=fr)
        assert plan.repair_needed
        assert plan.repair_type == RepairType.SELECTOR_REPAIR
        assert plan.status == "pending_review"

    def test_plan_from_structure_diff(self):
        class SD: pass
        sd = SD(); sd.structure_changed = True; sd.change_score = 0.7; sd.failed_selectors = [".title", ".price"]
        planner = RepairPlanner()
        plan = planner.plan_repair(url="http://x.com", structure_diff=sd)
        assert plan.repair_needed
        assert plan.repair_type == RepairType.SELECTOR_REPAIR
        assert plan.priority == RepairPriority.HIGH

    def test_plan_with_field_candidates(self):
        candidates = [
            {"field": "title", "candidate_selectors": [
                {"selector": "h1.new", "confidence": 0.9, "evidence": "found"}
            ]}
        ]
        planner = RepairPlanner()
        # Providing field_candidates alone does NOT auto-set repair_needed (needs failure_report too)
        plan = planner.plan_repair(url="http://x.com", field_candidates=candidates)
        assert plan.field_candidates == candidates
        assert plan.status == "pending_review"
        # With failure_report, it should set repair_needed
        class FR: pass
        fr = FR(); fr.failure_type = "selector_failed"; fr.severity = "medium"
        fr.reason = "test"; fr.recommend_ai_parser = False; fr.recommend_selector_repair = True
        plan2 = planner.plan_repair(url="http://x.com", failure_report=fr, field_candidates=candidates)
        assert plan2.repair_needed

    def test_plan_never_recommends_on_mode_without_enough_data(self):
        planner = RepairPlanner()
        plan = planner.plan_repair(url="http://x.com")
        assert not plan.switch_to_on_mode_recommended
        assert "do NOT" in plan.switch_to_on_mode_reason.lower() or "manual" in plan.switch_to_on_mode_reason.lower()

    def test_status_always_pending_review(self):
        planner = RepairPlanner()
        plan = planner.plan_repair(url="http://x.com")
        assert plan.status == "pending_review"

    def test_plan_to_dict(self):
        planner = RepairPlanner()
        plan = planner.plan_repair(url="http://x.com", site_id="test")
        d = plan.to_dict()
        assert d["status"] == "pending_review"
        assert d["url"] == "http://x.com"
        assert "actions" in d

    def test_plan_with_ai_success_adds_note(self):
        class FR: pass
        fr = FR(); fr.failure_type = "low_quality_parse"; fr.severity = "low"
        fr.recommend_ai_parser = True; fr.recommend_selector_repair = False; fr.reason = "low quality"
        planner = RepairPlanner()
        plan = planner.plan_repair(url="http://x.com", failure_report=fr, ai_parse_success=True)
        assert plan.ai_parser_recommended
        assert any("verify" in a.action.lower() for a in plan.actions)

    def test_plan_from_shadow_failed_entry(self):
        planner = RepairPlanner()
        entry = {"acs_success": False, "acs_completeness": 0, "acs_error": "parse error"}
        plan = planner.plan_from_shadow(url="http://x.com", shadow_entry=entry)
        assert plan.repair_needed

    def test_plan_from_shadow_success_entry(self):
        planner = RepairPlanner()
        entry = {"acs_success": True, "acs_quality": "high", "acs_completeness": 80, "acs_error": ""}
        plan = planner.plan_from_shadow(url="http://x.com", shadow_entry=entry)
        assert not plan.repair_needed

    def test_repair_type_enum_values(self):
        assert RepairType.SELECTOR_REPAIR.value == "selector_repair"
        assert RepairType.NO_ACTION.value == "no_action"
        assert RepairType.AI_FALLBACK.value == "ai_fallback"

    def test_no_action_when_nothing_wrong(self):
        planner = RepairPlanner()
        plan = planner.plan_repair(url="http://x.com")
        assert plan.repair_type == RepairType.NO_ACTION
        assert any("no repair" in a.action.lower() for a in plan.actions) or not plan.repair_needed

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
