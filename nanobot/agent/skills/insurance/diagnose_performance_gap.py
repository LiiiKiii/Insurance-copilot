"""Business performance diagnosis using the available data and pace Tools."""

from __future__ import annotations

from typing import Any

from .base import InsuranceSkill, contains_any


class DiagnosePerformanceGapSkill(InsuranceSkill):
    name = "diagnose_performance_gap"
    priority = 10
    description = "Diagnose overall performance, competition gaps and current pace."
    trigger_keywords = (
        "业绩缺口", "業績缺口", "业绩诊断", "業績診斷", "业绩怎么", "業績怎麼",
        "业绩如何", "業績如何", "业绩分析", "業績分析", "完成率", "达成率",
        "達成率", "保费做了多少", "保費做了多少", "全面诊断", "全面診斷",
        "整体业绩", "整體業績", "performance gap", "performance diagnosis",
        "analyze my performance", "analyse my performance",
    )
    required_tools = ("get_performance_snapshot", "get_competition_status",
                      "get_pending_policies")

    def match_intent(self, user_message: str) -> bool:
        return isinstance(user_message, str) and contains_any(user_message, self.trigger_keywords)

    def get_skill_prompt(self, context: dict[str, Any]) -> str:
        steps = [
            "In order, call get_performance_snapshot(agent_id=<signed-in agent>), "
            "get_competition_status(agent_id=<signed-in agent>, include_honors=true), "
            "then get_pending_policies(agent_id=<signed-in agent>)."
        ]
        if "calculate_run_rate" in context["available_tools"]:
            steps.append(
                "For a monetary performance metric with compatible current and target values, "
                "calculate_run_rate(current=<snapshot current>, target=<snapshot target>); "
                "these are numeric values, not agent_id. Do not apply monetary pace to policy counts."
            )
        steps.append(
            "Use four sections: performance snapshot, competition gaps ordered by urgency, "
            "pace analysis, coaching actions. Show each source unit. Competition gap is nominal. "
            "Pending premium is not approved or achieved; no verified pending-adjusted gap "
            "calculator is available in this workflow. Omit unsupported estimates."
        )
        return "\n".join(steps)
