"""Target breakdown and coaching guidance backed by the planning Tool."""

from __future__ import annotations

import re
from typing import Any

from .base import BUSINESS_TERMS, InsuranceSkill, contains_any


class DecomposeGoalSkill(InsuranceSkill):
    name = "decompose_goal_and_advise"
    priority = 30
    description = "Break down a target into a weekly plan and daily actions."
    trigger_keywords = (
        "拆解", "计划", "計劃", "怎么追", "怎麼追", "每周", "每週",
        "行动建议", "行動建議", "帮我追", "幫我追", "冲刺", "衝刺",
        "追上", "追得上", "怎么做", "怎麼做", "追单", "追單",
        "如何达成", "如何達成",
    )
    required_tools = ("get_competition_status", "generate_chase_plan")

    def match_intent(self, user_message: str) -> bool:
        if not isinstance(user_message, str):
            return False
        chinese = contains_any(user_message, self.trigger_keywords) and contains_any(
            user_message, BUSINESS_TERMS
        )
        english = bool(re.search(
            r"\b(?:weekly\s+(?:target|goal)\s+plan|"
            r"plan\s+to\s+(?:reach|achieve)\s+(?:my\s+)?(?:target|goal)|"
            r"(?:create|make|build)\s+(?:a\s+)?(?:weekly\s+)?(?:target|goal)\s+plan)\b",
            user_message, re.IGNORECASE,
        ))
        return chinese or english

    def get_skill_prompt(self, context: dict[str, Any]) -> str:
        tools = context["available_tools"]
        steps = [
            "Call get_competition_status(agent_id=<signed-in agent>), select the named "
            "competition, then generate_chase_plan(agent_id=<signed-in agent>, "
            "competition_id=<selected ID>). Use its weekly_plans and daily_actions "
            "as the source of weekly targets and P0/P1 actions."
        ]
        if "get_attribution_analysis" in tools and "generate_improvement_advice" in tools:
            steps.append(
                "For coaching, call get_attribution_analysis(agent_id=<signed-in agent>) "
                "then generate_improvement_advice(agent_id=<signed-in agent>)."
            )
        if "search_best_practice" in tools:
            steps.append(
                "For an evidenced weak dimension, search_best_practice(topic=<dimension>, "
                "search_mode='keyword') and cite the returned guidance."
            )
        steps.append(
            "Show target, deadline, a weekly plan and a P0-first daily checklist. "
            "The chase plan's actual_gap is a pending-premium-adjusted planning estimate, "
            "not a verified open gap or issued business. Preserve each source unit; "
            "omit unavailable feasibility or improvement claims."
        )
        return "\n".join(steps)
