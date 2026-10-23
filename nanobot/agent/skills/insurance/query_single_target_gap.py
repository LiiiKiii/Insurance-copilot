"""Focused gap answer for one named competition or honour."""

from __future__ import annotations

from typing import Any

from .base import InsuranceSkill, contains_any


class QuerySingleTargetGapSkill(InsuranceSkill):
    name = "query_single_target_gap"
    priority = 5
    description = "Answer the gap for one named target without a full diagnosis."
    trigger_keywords = ("mdrt", "cot", "ttt", "ida", "荣誉", "榮譽", "竞赛", "競賽")
    required_tools = ("get_competition_status",)
    _gap_phrases = (
        "差多少", "還差", "还差", "離目標", "离目标", "離達標", "离达标",
        "距離達標", "距离达标", "gap", "shortfall", "how far",
    )

    def match_intent(self, user_message: str) -> bool:
        return (isinstance(user_message, str)
                and contains_any(user_message, self.trigger_keywords)
                and contains_any(user_message, self._gap_phrases))

    def get_skill_prompt(self, context: dict[str, Any]) -> str:
        tools = context["available_tools"]
        steps = [
            "Use get_competition_status(agent_id=<signed-in agent>, include_honors=true) "
            "and identify only the target named by the user. The returned gap is the stored "
            "nominal gap; use its own unit and deadline."
        ]
        if "get_performance_snapshot" in tools:
            steps.append(
                "For MDRT/COT/IDA, get_performance_snapshot(agent_id=<signed-in agent>, "
                "metrics=['protection_premium']) only if its metric is needed for context."
            )
        if "get_pending_policies" in tools:
            steps.append(
                "Only if asked about pending premium, use get_pending_policies(agent_id=<signed-in agent>); "
                "pending is unapproved and must not be represented as achieved premium."
            )
        steps.append(
            "Answer current, target, nominal gap, deadline and a cautious next step in "
            "2-4 sentences. If feasibility evidence is absent, say it cannot be assessed. "
            "Do not output a full performance table or a list of unrelated competitions."
        )
        return "\n".join(steps)
