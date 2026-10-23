"""Deterministic, fail-closed selection of insurance workflow guidance."""

from __future__ import annotations

from typing import Any

from .analyze_underperformance import AnalyzeUnderperformanceSkill
from .base import InsuranceSkill
from .check_feasibility import CheckFeasibilitySkill
from .decompose_goal_and_advise import DecomposeGoalSkill
from .diagnose_performance_gap import DiagnosePerformanceGapSkill
from .query_single_target_gap import QuerySingleTargetGapSkill


# These are the New Repo Tool schemas, not signatures of Original pure functions.
_EXPECTED_REQUIRED = {
    "get_performance_snapshot": frozenset({"agent_id"}),
    "get_competition_status": frozenset({"agent_id"}),
    "get_pending_policies": frozenset({"agent_id"}),
    "calculate_run_rate": frozenset({"current", "target"}),
    "generate_chase_plan": frozenset({"agent_id"}),
    "assess_gap_feasibility": frozenset({"actual_gap", "days_remaining", "monthly_avg"}),
    "get_attribution_analysis": frozenset({"agent_id"}),
    "generate_improvement_advice": frozenset({"agent_id"}),
    "search_best_practice": frozenset({"topic"}),
}
_EXPECTED_PROPERTIES = {
    "get_performance_snapshot": {"agent_id": "string", "metrics": "array"},
    "get_competition_status": {"agent_id": "string", "competition_id": "string",
                               "include_honors": "boolean"},
    "get_pending_policies": {"agent_id": "string"},
    "calculate_run_rate": {"current": "number", "target": "number"},
    "generate_chase_plan": {"agent_id": "string", "competition_id": "string"},
    "assess_gap_feasibility": {"actual_gap": "number", "days_remaining": "integer",
                               "monthly_avg": "number", "unit": "string"},
    "get_attribution_analysis": {"agent_id": "string"},
    "generate_improvement_advice": {"agent_id": "string"},
    "search_best_practice": {"topic": "string", "search_mode": "string"},
}
# Arguments present in each Skill's actual Tool calls, including conditional
# calls. A newly required argument is safe only for Skills that supply it.
_SKILL_CALL_ARGUMENTS = {
    "query_single_target_gap": {
        "get_competition_status": {"agent_id", "include_honors"},
        "get_performance_snapshot": {"agent_id", "metrics"},
        "get_pending_policies": {"agent_id"},
    },
    "diagnose_performance_gap": {
        "get_performance_snapshot": {"agent_id"},
        "get_competition_status": {"agent_id", "include_honors"},
        "get_pending_policies": {"agent_id"},
        "calculate_run_rate": {"current", "target"},
    },
    "check_feasibility": {
        "get_competition_status": {"agent_id"},
        "generate_chase_plan": {"agent_id", "competition_id"},
        "assess_gap_feasibility": {"actual_gap", "days_remaining", "monthly_avg", "unit"},
    },
    "decompose_goal_and_advise": {
        "get_competition_status": {"agent_id"},
        "generate_chase_plan": {"agent_id", "competition_id"},
        "get_attribution_analysis": {"agent_id"},
        "generate_improvement_advice": {"agent_id"},
        "search_best_practice": {"topic", "search_mode"},
    },
    "analyze_underperformance": {
        "get_performance_snapshot": {"agent_id"},
        "get_attribution_analysis": {"agent_id"},
        "generate_improvement_advice": {"agent_id"},
        "search_best_practice": {"topic", "search_mode"},
    },
}
_MAX_USER_CHARS = 4096
_MAX_GUIDANCE_CHARS = 5000


def _compatible_tools(definitions: list[dict[str, Any]] | None) -> dict[str, frozenset[str]]:
    if not isinstance(definitions, list):
        return {}
    available: dict[str, frozenset[str]] = {}
    for definition in definitions:
        if not isinstance(definition, dict) or definition.get("type") != "function":
            continue
        function = definition.get("function")
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        if not isinstance(name, str) or name not in _EXPECTED_REQUIRED:
            continue
        parameters = function.get("parameters")
        if not isinstance(parameters, dict) or parameters.get("type") != "object":
            continue
        properties = parameters.get("properties")
        required = parameters.get("required")
        expected = _EXPECTED_REQUIRED[name]
        if (not isinstance(properties, dict) or not isinstance(required, list)
                or not all(isinstance(item, str) and item for item in required)
                or len(set(required)) != len(required)
                or not set(required).issubset(properties)
                or not expected.issubset(required)
                or any(not isinstance(properties.get(key), dict)
                       or properties[key].get("type") != kind
                       for key, kind in _EXPECTED_PROPERTIES[name].items())):
            continue
        if name == "assess_gap_feasibility":
            units = properties["unit"].get("enum")
            if not isinstance(units, list) or not {"USD", "HKD", "policies"}.issubset(units):
                continue
        available[name] = frozenset(required)
    return available


class SkillRegistry:
    """Match raw user intent; offer at most two skills with compatible Tools."""

    def __init__(self) -> None:
        self._skills: tuple[InsuranceSkill, ...] = (
            QuerySingleTargetGapSkill(),
            DiagnosePerformanceGapSkill(),
            CheckFeasibilitySkill(),
            DecomposeGoalSkill(),
            AnalyzeUnderperformanceSkill(),
        )

    def match(self, user_message: str) -> list[InsuranceSkill]:
        if not isinstance(user_message, str) or not user_message.strip() or len(user_message) > _MAX_USER_CHARS:
            return []
        return [skill for skill in self._skills if skill.match_intent(user_message)]

    def get_prompt_injection(
        self,
        user_message: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Return only static server-owned text; context supplies verified Tool schemas."""
        if not isinstance(context, dict):
            return ""
        schemas = _compatible_tools(context.get("tool_definitions"))
        if not schemas:
            return ""
        selected: list[tuple[InsuranceSkill, frozenset[str]]] = []
        for skill in sorted(self.match(user_message), key=lambda item: item.priority):
            arguments = _SKILL_CALL_ARGUMENTS.get(skill.name, {})
            available = frozenset(
                name for name, required in schemas.items()
                if name in arguments and required.issubset(arguments[name])
            )
            if set(skill.required_tools).issubset(available):
                selected.append((skill, available))
            if len(selected) == 2:
                break
        prompts = [f"[Insurance Skill: {skill.name}]\n"
                   f"{skill.get_skill_prompt({'available_tools': available})}"
                   for skill, available in selected]
        guidance = "\n\n".join(prompts)
        return guidance if len(guidance) <= _MAX_GUIDANCE_CHARS else ""
