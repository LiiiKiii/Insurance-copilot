"""Attribution-led underperformance guidance."""

from __future__ import annotations

import re
from typing import Any

from .base import BUSINESS_TERMS, InsuranceSkill, contains_any


class AnalyzeUnderperformanceSkill(InsuranceSkill):
    name = "analyze_underperformance"
    priority = 40
    description = "Find evidenced weaknesses and supported improvement actions."
    trigger_keywords = (
        "为什么", "為什麼", "归因", "歸因", "瓶颈", "瓶頸",
        "哪里出了问题", "哪裡出了問題", "没达标", "沒達標", "原因",
        "差在哪", "差在哪裡", "为何", "為何", "问题在哪", "問題在哪",
    )
    required_tools = ("get_performance_snapshot", "get_attribution_analysis",
                      "generate_improvement_advice")

    def match_intent(self, user_message: str) -> bool:
        if not isinstance(user_message, str):
            return False
        chinese = contains_any(user_message, self.trigger_keywords) and contains_any(
            user_message, BUSINESS_TERMS
        )
        english = bool(re.search(
            r"\b(?:why\s+am\s+i\s+underperforming|"
            r"why\s+is\s+my\s+performance\s+(?:low|behind)|"
            r"(?:root\s+cause|bottleneck)\s+(?:of|in)\s+(?:my\s+)?performance)\b",
            user_message, re.IGNORECASE,
        ))
        return chinese or english

    def get_skill_prompt(self, context: dict[str, Any]) -> str:
        steps = [
            "In order, call get_performance_snapshot(agent_id=<signed-in agent>), "
            "get_attribution_analysis(agent_id=<signed-in agent>), then "
            "generate_improvement_advice(agent_id=<signed-in agent>). Use the advice "
            "tool's gap_pct, peer_avg, impact and P0/P1 actions only when returned."
        ]
        if "search_best_practice" in context["available_tools"]:
            steps.append(
                "For the evidenced top weakness, search_best_practice(topic=<weak dimension>, "
                "search_mode='keyword') and cite the returned guidance."
            )
        steps.append(
            "Show a peer comparison, the supported strongest and weakest dimensions, "
            "and concrete P0/P1 improvements. Do not claim period trends or rankings: "
            "those Tools are not available in this workflow. Never infer missing values."
        )
        return "\n".join(steps)
