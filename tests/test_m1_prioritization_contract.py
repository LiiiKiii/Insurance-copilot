"""Offline M1 checks for the registered M4 tool and M2 scenario payloads."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from nanobot.agent.tools.insurance.planning_layer.prioritization import (
    PrioritizeFollowupsTool,
    prioritize_followups,
)
from nanobot.agent.tools.registry import ToolRegistry


_SCENARIOS = Path(__file__).resolve().parents[1] / "data" / "evaluation" / "m2_candidate_scenarios.json"


class M1PrioritizationContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_m2_scenario_passes_registered_tool_boundary(self) -> None:
        scenario = json.loads(_SCENARIOS.read_text(encoding="utf-8"))["scenarios"][0]
        registry = ToolRegistry()
        registry.register(PrioritizeFollowupsTool())
        payload = {
            key: scenario[key]
            for key in ("agent_id", "objective", "constraints", "candidates")
        }

        content, status = await registry.execute_with_status("prioritize_followups", payload)

        self.assertEqual(status, "completed")
        result = json.loads(content)
        self.assertEqual(result["agent_id"], scenario["agent_id"])
        self.assertEqual(result["eligible_count"], 6)
        self.assertEqual(len(result["recommendations"]), 5)

    async def test_repaired_schema_rejects_malformed_candidate_items(self) -> None:
        """Keep the repaired M4 nested schema aligned with its ranker."""
        tool = PrioritizeFollowupsTool()
        payload = {
            "agent_id": "AGT001",
            "objective": {"open_gap": 100},
            "candidates": [
                {},
                {"candidate_id": "P1", "expected_contribution": "invalid",
                 "urgency": 0.5, "actionability": 0.5},
                {"candidate_id": "P2", "expected_contribution": 10,
                 "urgency": 1.5, "actionability": 0.5},
            ],
        }

        item_schema = tool.to_schema()["function"]["parameters"]["properties"]["candidates"]["items"]
        self.assertEqual(set(item_schema["required"]), {
            "candidate_id", "expected_contribution", "urgency", "actionability",
        })
        errors = tool.validate_params(tool.cast_params(payload))
        self.assertTrue(any("candidate_id" in error for error in errors))
        self.assertTrue(any("expected_contribution" in error for error in errors))
        self.assertTrue(any("urgency" in error for error in errors))
        self.assertEqual(
            [row["reason"] for row in prioritize_followups(payload)["excluded_candidates"]],
            ["missing_candidate_id", "invalid_expected_contribution", "invalid_urgency"],
        )


if __name__ == "__main__":
    unittest.main()
