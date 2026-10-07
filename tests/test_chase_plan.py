"""Baseline contract tests for the template-based chase-plan tool."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from nanobot.agent.tools.insurance.planning_layer.chase_plan import (
    GenerateChasePlanTool,
)


HKD_TEMPLATES = {
    "hkd_actions": [
        {
            "priority": "P0",
            "template": "Produce HKD {daily_premium_needed:,} per day",
        }
    ],
    "non_hkd_actions": [],
}


def _competition(
    competition_id: str,
    *,
    name: str = "Annual Challenge",
    gap: float = 70_000,
    days_remaining: int = 28,
    deadline: str = "2026-12-31",
    unit: str = "HKD",
) -> dict:
    """Build the data-layer contract consumed by the chase-plan tool."""
    return {
        "id": competition_id,
        "name": name,
        "gap": gap,
        "days_remaining": days_remaining,
        "deadline": deadline,
        "unit": unit,
        "tags": [],
    }


class GenerateChasePlanToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.tool = GenerateChasePlanTool(Path(self.temp_dir.name))

    async def test_generates_equal_weekly_targets_from_netted_hkd_gap(self) -> None:
        competitions = [_competition("C1")]
        performance = SimpleNamespace(
            protection_premium_current=120_000,
            protection_premium_target=240_000,
            pending_premium_current=14_000,
        )

        with (
            patch(
                "nanobot.agent.tools.insurance.planning_layer.chase_plan.load_competitions_from_db",
                return_value=competitions,
            ),
            patch(
                "nanobot.agent.tools.insurance.planning_layer.chase_plan.load_performance_row",
                return_value=performance,
            ),
            patch(
                "nanobot.agent.tools.insurance.planning_layer.chase_plan.compute_run_rate",
                return_value={"monthly_avg": 20_000},
            ),
            patch(
                "nanobot.agent.tools.insurance.planning_layer.chase_plan._load_action_templates",
                return_value=HKD_TEMPLATES,
            ),
        ):
            result = json.loads(
                await self.tool.execute(agent_id="A1", competition_id="C1")
            )

        self.assertEqual(result["actual_gap"], 56_000)
        self.assertEqual(result["pending_deduction"], 14_000)
        self.assertEqual(result["weeks_remaining"], 4)
        self.assertEqual(result["weekly_target"], 14_000)
        self.assertEqual(len(result["weekly_plans"]), 4)
        self.assertEqual(result["weekly_plans"][0]["target"], "HKD 14,000")
        self.assertEqual(
            result["daily_actions"],
            [{"priority": "P0", "action": "Produce HKD 2,000 per day"}],
        )

    async def test_omitted_id_selects_most_urgent_open_competition(self) -> None:
        competitions = [
            _competition("LATER", name="Later", days_remaining=42),
            _competition("SOON", name="Soon", days_remaining=14, gap=14_000),
        ]

        with (
            patch(
                "nanobot.agent.tools.insurance.planning_layer.chase_plan.load_competitions_from_db",
                return_value=competitions,
            ),
            patch(
                "nanobot.agent.tools.insurance.planning_layer.chase_plan.load_performance_row",
                return_value=None,
            ),
            patch(
                "nanobot.agent.tools.insurance.planning_layer.chase_plan.compute_run_rate",
                return_value={"monthly_avg": 0},
            ),
            patch(
                "nanobot.agent.tools.insurance.planning_layer.chase_plan._load_action_templates",
                return_value=HKD_TEMPLATES,
            ),
        ):
            result = json.loads(await self.tool.execute(agent_id="A1"))

        self.assertEqual(result["competition_id"], "SOON")
        self.assertEqual(result["competition_name"], "Soon")

    async def test_returns_message_when_pending_covers_every_gap(self) -> None:
        performance = SimpleNamespace(
            protection_premium_current=0,
            protection_premium_target=1,
            pending_premium_current=70_000,
        )

        with (
            patch(
                "nanobot.agent.tools.insurance.planning_layer.chase_plan.load_competitions_from_db",
                return_value=[_competition("C1")],
            ),
            patch(
                "nanobot.agent.tools.insurance.planning_layer.chase_plan.load_performance_row",
                return_value=performance,
            ),
        ):
            result = json.loads(await self.tool.execute(agent_id="A1"))

        self.assertEqual(
            result,
            {
                "message": (
                    "All competition targets have been met or their gaps are "
                    "covered by pending premiums!"
                )
            },
        )

    async def test_returns_error_for_unknown_competition(self) -> None:
        with (
            patch(
                "nanobot.agent.tools.insurance.planning_layer.chase_plan.load_competitions_from_db",
                return_value=[_competition("C1")],
            ),
            patch(
                "nanobot.agent.tools.insurance.planning_layer.chase_plan.load_performance_row",
                return_value=None,
            ),
        ):
            result = json.loads(
                await self.tool.execute(agent_id="A1", competition_id="UNKNOWN")
            )

        self.assertEqual(result, {"error": "Competition data not found"})

    async def test_returns_stable_error_when_competition_query_fails(self) -> None:
        with patch(
            "nanobot.agent.tools.insurance.planning_layer.chase_plan.load_competitions_from_db",
            side_effect=RuntimeError("database unavailable"),
        ):
            result = json.loads(await self.tool.execute(agent_id="A1"))

        self.assertEqual(result, {"error": "Data query failed"})


if __name__ == "__main__":
    unittest.main()
