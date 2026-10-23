"""Feasibility guidance with an explicitly labelled planning estimate."""

from __future__ import annotations

import re
from typing import Any

from .base import BUSINESS_TERMS, InsuranceSkill, contains_any


class CheckFeasibilitySkill(InsuranceSkill):
    name = "check_feasibility"
    priority = 20
    description = "Assess whether a named target is feasible using tool-derived inputs."
    trigger_keywords = (
        "能完成吗", "能完成嗎", "来得及", "來得及", "有希望", "能追上",
        "还有机会", "還有機會", "可行", "多久截止", "还剩多少天",
        "還剩多少天", "有没有希望", "有沒有希望", "能赶上", "能趕上",
    )
    required_tools = ("get_competition_status", "generate_chase_plan",
                      "assess_gap_feasibility")

    def match_intent(self, user_message: str) -> bool:
        if not isinstance(user_message, str):
            return False
        chinese = contains_any(user_message, self.trigger_keywords) and contains_any(
            user_message, BUSINESS_TERMS
        )
        english = bool(re.search(
            r"\b(?:can\s+i\s+(?:still\s+)?(?:achieve|reach|meet)|"
            r"is\s+(?:my|the)\s+(?:target|goal)\s+feasible|"
            r"can\s+i\s+catch\s+up|(?:target|goal)\s+feasib(?:le|ility))\b",
            user_message, re.IGNORECASE,
        )) and contains_any(user_message, BUSINESS_TERMS)
        return chinese or english

    def get_skill_prompt(self, context: dict[str, Any]) -> str:
        return (
            "Call get_competition_status(agent_id=<signed-in agent>) and select the "
            "user's target. Then call generate_chase_plan(agent_id=<signed-in agent>, "
            "competition_id=<selected ID>). If its result has finite numeric actual_gap, "
            "days_remaining and monthly_avg_reference, call assess_gap_feasibility "
            "only for a USD plan: the current monthly_avg_reference comes from USD "
            "protection premium and is not a HKD or policy-count baseline. Call "
            "assess_gap_feasibility(actual_gap=<plan actual_gap>, "
            "days_remaining=<plan days_remaining>, monthly_avg=<plan monthly_avg_reference>, "
            "unit='USD'). Never pass agent_id to that calculation. "
            "Report the tool's level, daily_needed and probability_pct only if returned. "
            "Label the plan gap and probability as estimates, never verified achievement or "
            "approval of pending policies. For HKD or policy-count plans, or if inputs "
            "are absent, state that feasibility cannot be determined from this baseline; "
            "end with one supported next action."
        )
