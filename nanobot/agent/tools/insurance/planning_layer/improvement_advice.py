"""Planning Layer: generate_improvement_advice — prioritized actions from attribution gaps."""
import json
from pathlib import Path
from typing import Any
from nanobot.agent.tools.base import Tool
from nanobot.agent.tools.insurance.data_layer._db import db_error, load_attribution_row


# Advice templates keyed by metric/dimension keyword
ADVICE_TEMPLATES = {
    "lead_followup": {
        "conversion_rate": {
            "action": "Spend 30 minutes at 16:00 each day calling back leads that have not been followed up, with the goal of increasing this week's follow-up rate from {value:.0%} to {target:.0%}",
            "expected": "Each 10% increase in lead conversion rate is expected to add HKD 30,000-50,000 in monthly premium",
        },
        "response_time_hours": {
            "action": "Make first contact with every new lead within 24 hours (set a CRM reminder); reduce the current average of {value} hours to within 24 hours",
            "expected": "Timely follow-up can improve conversion rates by approximately 15-20%",
        },
        "followup_count": {
            "action": "Follow up each lead at least three times (call → proposal → meeting); increase the current average of {value} follow-ups",
            "expected": "The conversion rate after three complete follow-ups is 2.5 times that after one follow-up",
        },
    },
    "policy_type": {
        "protection_ratio": {
            "action": "Conduct a needs analysis before every quotation and recommend a 60:40 protection-to-savings product ratio; the current ratio is {value:.0%}",
            "expected": "Average case premium can increase from HKD {current:,} to HKD {target:,}",
        },
        "avg_case_size": {
            "action": "Starting this month, pair every main policy with at least one rider (critical illness + medical) to increase average case premium",
            "expected": "Adding riders can increase average case premium by 30-40%",
        },
    },
    "activity": {
        "client_events_hosted": {
            "action": "Host one client event this month (seminar/tea gathering) and invite 10 clients; increase from the current {value} events",
            "expected": "The closing rate after client events can increase by 2-3 times",
        },
        "seminar_attended": {
            "action": "Attend one company training session or industry seminar each week to improve product knowledge and sales skills",
            "expected": "Systematic training significantly improves sales confidence and closing rates",
        },
    },
    "training": {
        "ai_training_sessions": {
            "action": "Complete two AI coaching sessions each week, focusing on objection-handling scenarios; {value} sessions have currently been completed",
            "expected": "AI coaching completion is positively correlated with average case premium (company data)",
        },
    },
}


def _get_advice(dimension: str, metric: str, value: Any, peer_avg: Any) -> dict | None:
    """Get advice template for a specific dimension/metric combination."""
    dim_advice = ADVICE_TEMPLATES.get(dimension, {})
    template = dim_advice.get(metric)
    if not template:
        # Generic advice
        return {
            "action": f"Prioritise improving {metric}: current value {value}, peer average {peer_avg}, with a significant gap",
            "expected": "Performance is expected to improve after this gap is addressed",
        }
    try:
        action = template["action"].format(
            value=value,
            peer_avg=peer_avg,
            target=peer_avg,
            current=value,
        )
    except (KeyError, ValueError):
        action = template["action"]
    return {"action": action, "expected": template["expected"]}


class GenerateImprovementAdviceTool(Tool):
    """Generate prioritized, actionable improvement advice based on attribution gaps.
    Part of Planning Layer — converts attribution analysis into specific daily actions."""

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "generate_improvement_advice"

    @property
    def description(self) -> str:
        return (
            "[Planning Layer] Generate prioritised, specific improvement actions based on attribution gap analysis."
            "Each recommendation includes a priority (P0/P1/P2), a concrete daily action, and its expected effect."
            "Call calc_attribution_gap first to obtain the gap analysis results."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent ID"},
                "top_n": {"type": "integer", "description": "Return the top N most important recommendations; default 5"},
            },
            "required": ["agent_id"],
        }

    async def execute(self, **kwargs: Any) -> str:
        agent_id = kwargs["agent_id"]
        top_n = max(int(kwargs.get("top_n", 5)), 1)

        try:
            row = load_attribution_row(agent_id)
        except Exception as e:
            return db_error(e)

        if not row:
            return json.dumps({"error": f"Agent {agent_id} not found"}, ensure_ascii=False)

        try:
            data = json.loads(row.data_json)
        except (TypeError, json.JSONDecodeError):
            return json.dumps({"error": f"Invalid attribution data format for agent {agent_id}"}, ensure_ascii=False)

        from nanobot.agent.tools.insurance.reasoning_layer.attribution_gap import compute_attribution_gap
        dimensions = data.get("dimensions", data) if isinstance(data, dict) else {}
        gaps = compute_attribution_gap(dimensions)
        weaknesses = [g for g in gaps if g["is_weakness"]]

        advice_list = []
        for i, weakness in enumerate(weaknesses[:top_n]):
            priority = "P0" if i == 0 else ("P1" if i <= 2 else "P2")
            adv = _get_advice(
                weakness["dimension"],
                weakness["metric"],
                weakness["value"],
                weakness["peer_avg"],
            )
            advice_list.append({
                "priority": priority,
                "dimension": weakness["dimension"],
                "metric_label": weakness["label"],
                "gap_pct": weakness["gap_pct"],
                "impact": weakness["impact"],
                "action": adv["action"] if adv else "",
                "expected_effect": adv["expected"] if adv else "",
                "current_value": weakness["value"],
                "peer_avg": weakness["peer_avg"],
                "unit": weakness["unit"],
            })

        return json.dumps({
            "agent_id": agent_id,
            "period": row.period,
            "total_weaknesses": len(weaknesses),
            "advice": advice_list,
        }, ensure_ascii=False, indent=2)
