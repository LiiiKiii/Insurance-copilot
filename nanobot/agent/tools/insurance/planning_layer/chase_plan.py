"""Generate the existing template-based week-by-week catch-up plan.

This module is the A2 planning baseline.  It converts an already calculated
competition gap into equal weekly targets and a configurable action checklist.
It deliberately does not score customer opportunities, rank policies, or
implement the optimisation model planned for a later coursework round.
"""
import json
import logging
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from nanobot.agent.tools.base import Tool
from nanobot.agent.tools.insurance.reasoning_layer.gap_analysis import compute_gap_analysis
from nanobot.agent.tools.insurance.reasoning_layer.run_rate import compute_run_rate
from nanobot.agent.tools.insurance.data_layer._db import load_competitions_from_db, load_performance_row

logger = logging.getLogger(__name__)

# ── Default action templates (fallback if config file not found) ──────────────
_DEFAULT_HKD_ACTIONS = [
    {"priority": "P0", "template": "Maintain daily production of HKD {daily_premium_needed:,} and prioritise high-value policies"},
    {"priority": "P0", "template": "Review the three clients most likely to close at 09:00 each day and follow up with each one"},
    {"priority": "P0", "template": "Contact every quoted client who has not been followed up within 30 days this week and ask about their concerns"},
    {"priority": "P1", "template": "Ask each existing client for one referral and explain the current competition target"},
    {"priority": "P1", "template": "Update case progress before the end of each workday and confirm the day's outcomes"},
    {"priority": "P2", "template": "Collaborate with a colleague on cases and introduce prospective clients to each other"},
]
_DEFAULT_NON_HKD_ACTIONS = [
    {"priority": "P0", "template": "Submit {per_week} {unit} this week and contact at least two prospective clients each day"},
    {"priority": "P0", "template": "Prioritise clients who have already expressed interest and move their applications towards completion"},
    {"priority": "P1", "template": "Confirm the day's outcomes before the end of each workday"},
]


_templates_cache: tuple[float, dict] | None = None
_TEMPLATES_CACHE_TTL = 60  # seconds


def _load_action_templates(workspace: Path | None = None) -> dict:
    """Load action templates from JSON config, with TTL cache and fallback to hardcoded defaults."""
    global _templates_cache
    now = time.monotonic()
    if _templates_cache is not None:
        cached_at, cached = _templates_cache
        if now - cached_at < _TEMPLATES_CACHE_TTL:
            return cached

    paths: list[Path] = []
    if workspace:
        paths.append(workspace / "data" / "config" / "action_templates.json")
    paths.append(Path(__file__).resolve().parent.parent.parent.parent.parent.parent / "data" / "config" / "action_templates.json")
    for p in paths:
        if p.exists():
            try:
                result = json.loads(p.read_text(encoding="utf-8"))
                _templates_cache = (now, result)
                return result
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load action templates from %s: %s", p, e)
    defaults = {"hkd_actions": _DEFAULT_HKD_ACTIONS, "non_hkd_actions": _DEFAULT_NON_HKD_ACTIONS}
    _templates_cache = (now, defaults)
    return defaults


class GenerateChasePlanTool(Tool):
    """Generate a structured week-by-week chase plan for a competition.
    Part of Planning Layer — produces weekly targets + daily action checklist."""

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "generate_chase_plan"

    @property
    def description(self) -> str:
        return (
            "[Planning Layer] Generate a weekly catch-up plan for a specified competition."
            "Automatically calculate weekly targets, required daily production, and a concrete action checklist."
            "Base the plan on the actual gap (after deducting pending premium) and historical average monthly production."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent ID"},
                "competition_id": {
                    "type": "string",
                    "description": "Competition ID (optional); if omitted, select the most urgent competition",
                },
            },
            "required": ["agent_id"],
        }

    async def execute(self, **kwargs: Any) -> str:
        agent_id = kwargs["agent_id"]
        comp_id = kwargs.get("competition_id")

        # Load competitions from DB
        try:
            competitions = load_competitions_from_db(self._workspace, agent_id)
        except Exception:
            return json.dumps({"error": "Data query failed"}, ensure_ascii=False)

        # Retrieve performance data from the ORM
        pending = 0
        pp_current = 0
        pp_target = 1
        try:
            perf = load_performance_row(agent_id)
            if perf:
                pp_current = perf.protection_premium_current or 0
                pp_target = perf.protection_premium_target or 1
                pending = perf.pending_premium_current or 0
        except Exception:
            pass

        run_rate = compute_run_rate(pp_current, pp_target)
        monthly_avg = run_rate["monthly_avg"]

        # Select competition
        gap_analyses = compute_gap_analysis(competitions, pending)

        if comp_id:
            comp = next((c for c in competitions if c.get("id") == comp_id), None)
            gap_info = next((g for g in gap_analyses if g.get("competition_id") == comp_id), None)
        else:
            # Pick most urgent with positive gap
            urgent = [
                (c, g) for c, g in zip(competitions, gap_analyses)
                if (g.get("actual_gap") or 0) > 0
            ]
            if not urgent:
                return json.dumps({"message": "All competition targets have been met or their gaps are covered by pending premiums!"}, ensure_ascii=False)
            comp, gap_info = sorted(urgent, key=lambda x: x[0].get("days_remaining", 9999))[0]

        if not comp or not gap_info:
            return json.dumps({"error": "Competition data not found"}, ensure_ascii=False)

        actual_gap = gap_info.get("actual_gap", 0)
        days_remaining = comp.get("days_remaining", 30)
        unit = comp.get("unit", "HKD")
        deadline = comp.get("deadline", "")
        today = date.today()

        # Generate weekly breakdown
        weeks = max(round(days_remaining / 7), 1)
        weekly_target = round(actual_gap / weeks)
        weekly_plans = []

        for w in range(1, weeks + 1):
            week_start = today + timedelta(weeks=w - 1)
            week_end = min(today + timedelta(weeks=w) - timedelta(days=1), date.fromisoformat(deadline) if deadline else today + timedelta(days=days_remaining))
            remaining_after = max(actual_gap - weekly_target * w, 0)

            if unit == "HKD":
                weekly_plans.append({
                    "week": f"Week {w} ({week_start.strftime('%m/%d')}-{week_end.strftime('%m/%d')})",
                    "target": f"HKD {weekly_target:,}",
                    "cumulative_target": f"HKD {weekly_target * w:,}",
                    "remaining_after": f"HKD {remaining_after:,}",
                })
            else:
                weekly_plans.append({
                    "week": f"Week {w}",
                    "target": f"{round(actual_gap / weeks)}{unit}",
                    "remaining_after": f"{remaining_after}{unit}",
                })

        # Daily action list
        daily_premium_needed = round(actual_gap / days_remaining) if days_remaining > 0 else 0

        # Load action templates from config
        templates = _load_action_templates(self._workspace)
        per_week = round(actual_gap / weeks)
        fmt_vars = {
            "daily_premium_needed": daily_premium_needed,
            "per_week": per_week,
            "unit": unit,
        }

        if unit == "HKD":
            raw_templates = templates.get("hkd_actions", _DEFAULT_HKD_ACTIONS)
        else:
            raw_templates = templates.get("non_hkd_actions", _DEFAULT_NON_HKD_ACTIONS)

        daily_actions = []
        for t in raw_templates:
            try:
                action_text = t["template"].format(**fmt_vars)
            except (KeyError, ValueError):
                action_text = t["template"]
            daily_actions.append({"priority": t["priority"], "action": action_text})

        return json.dumps({
            "agent_id": agent_id,
            "competition_name": comp.get("name"),
            "competition_id": comp.get("id"),
            "actual_gap": actual_gap,
            "nominal_gap": gap_info.get("nominal_gap"),
            "pending_deduction": gap_info.get("pending_deduction", 0),
            "deadline": deadline,
            "days_remaining": days_remaining,
            "weeks_remaining": weeks,
            "weekly_target": weekly_target,
            "unit": unit,
            "monthly_avg_reference": monthly_avg,
            "weekly_plans": weekly_plans,
            "daily_actions": daily_actions,
        }, ensure_ascii=False, indent=2)
