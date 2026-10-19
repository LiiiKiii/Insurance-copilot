"""A5 M4 baseline tests for the template-based planning tools."""

from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from nanobot.agent.tools.insurance.planning_layer.improvement_advice import (
    GenerateImprovementAdviceTool,
    _get_advice,
)


ATTRIBUTION_MODULE = (
    "nanobot.agent.tools.insurance.reasoning_layer.attribution_gap"
)


def _weakness(
    dimension: str,
    metric: str,
    *,
    value: float = 0.2,
    peer_avg: float = 0.5,
    label: str | None = None,
) -> dict:
    """Build the attribution-gap contract consumed by improvement advice."""
    return {
        "dimension": dimension,
        "metric": metric,
        "label": label or metric.replace("_", " ").title(),
        "value": value,
        "peer_avg": peer_avg,
        "gap_pct": 60.0,
        "impact": "high",
        "unit": "%",
        "is_weakness": True,
    }


class GenerateImprovementAdviceToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.tool = GenerateImprovementAdviceTool(Path(self.temp_dir.name))

    @staticmethod
    def _attribution_module(result: list[dict], calls: list[dict]) -> types.ModuleType:
        module = types.ModuleType(ATTRIBUTION_MODULE)

        def compute_attribution_gap(dimensions: dict) -> list[dict]:
            calls.append(dimensions)
            return result

        module.compute_attribution_gap = compute_attribution_gap
        return module

    def test_tool_contract_exposes_required_agent_and_optional_top_n(self) -> None:
        self.assertEqual(self.tool.name, "generate_improvement_advice")
        self.assertEqual(self.tool.parameters["required"], ["agent_id"])
        self.assertEqual(
            self.tool.parameters["properties"]["top_n"]["type"],
            "integer",
        )

    async def test_returns_stable_error_when_attribution_query_fails(self) -> None:
        with patch(
            "nanobot.agent.tools.insurance.planning_layer.improvement_advice.load_attribution_row",
            side_effect=RuntimeError("database unavailable"),
        ):
            result = json.loads(await self.tool.execute(agent_id="A1"))

        self.assertEqual(result, {"error": "Database query failed"})

    async def test_returns_error_when_agent_has_no_attribution_snapshot(self) -> None:
        with patch(
            "nanobot.agent.tools.insurance.planning_layer.improvement_advice.load_attribution_row",
            return_value=None,
        ):
            result = json.loads(await self.tool.execute(agent_id="A1"))

        self.assertEqual(result, {"error": "Agent A1 not found"})

    async def test_rejects_invalid_attribution_json(self) -> None:
        row = SimpleNamespace(period="2026-Q3", data_json="not-json")

        with patch(
            "nanobot.agent.tools.insurance.planning_layer.improvement_advice.load_attribution_row",
            return_value=row,
        ):
            result = json.loads(await self.tool.execute(agent_id="A1"))

        self.assertEqual(
            result,
            {"error": "Invalid attribution data format for agent A1"},
        )

    async def test_builds_prioritised_top_n_advice_from_dimensions(self) -> None:
        dimensions = {"lead_followup": {"conversion_rate": 0.2}}
        row = SimpleNamespace(
            period="2026-Q3",
            data_json=json.dumps({"dimensions": dimensions}),
        )
        gaps = [
            _weakness("lead_followup", "conversion_rate", label="Conversion rate"),
            _weakness("activity", "client_events_hosted", value=0, peer_avg=1),
            _weakness("training", "ai_training_sessions", value=1, peer_avg=4),
            _weakness("other", "referral_rate", value=0.1, peer_avg=0.3),
            {**_weakness("other", "healthy_metric"), "is_weakness": False},
        ]
        calls: list[dict] = []
        module = self._attribution_module(gaps, calls)

        with (
            patch(
                "nanobot.agent.tools.insurance.planning_layer.improvement_advice.load_attribution_row",
                return_value=row,
            ),
            patch.dict(sys.modules, {ATTRIBUTION_MODULE: module}),
        ):
            result = json.loads(
                await self.tool.execute(agent_id="A1", top_n=4)
            )

        self.assertEqual(calls, [dimensions])
        self.assertEqual(result["agent_id"], "A1")
        self.assertEqual(result["period"], "2026-Q3")
        self.assertEqual(result["total_weaknesses"], 4)
        self.assertEqual(
            [item["priority"] for item in result["advice"]],
            ["P0", "P1", "P1", "P2"],
        )
        self.assertIn("30 minutes", result["advice"][0]["action"])
        self.assertIn("referral_rate", result["advice"][3]["action"])

    async def test_top_n_is_clamped_to_at_least_one(self) -> None:
        row = SimpleNamespace(period="2026-Q3", data_json=json.dumps({}))
        gaps = [
            _weakness("activity", "client_events_hosted", value=0, peer_avg=1),
            _weakness("training", "ai_training_sessions", value=1, peer_avg=4),
        ]
        module = self._attribution_module(gaps, [])

        with (
            patch(
                "nanobot.agent.tools.insurance.planning_layer.improvement_advice.load_attribution_row",
                return_value=row,
            ),
            patch.dict(sys.modules, {ATTRIBUTION_MODULE: module}),
        ):
            result = json.loads(
                await self.tool.execute(agent_id="A1", top_n=0)
            )

        self.assertEqual(result["total_weaknesses"], 2)
        self.assertEqual(len(result["advice"]), 1)
        self.assertEqual(result["advice"][0]["priority"], "P0")


class ImprovementAdviceTemplateTests(unittest.TestCase):
    def test_known_template_formats_current_and_target_values(self) -> None:
        advice = _get_advice(
            "lead_followup",
            "conversion_rate",
            0.2,
            0.5,
        )

        self.assertIsNotNone(advice)
        self.assertIn("20%", advice["action"])
        self.assertIn("50%", advice["action"])

    def test_unknown_metric_uses_generic_advice(self) -> None:
        advice = _get_advice("other", "referral_rate", 0.1, 0.3)

        self.assertIsNotNone(advice)
        self.assertIn("referral_rate", advice["action"])
        self.assertIn("0.3", advice["action"])


if __name__ == "__main__":
    unittest.main()
