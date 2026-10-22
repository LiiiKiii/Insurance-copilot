"""Deterministic unit tests for the M4 candidate prioritisation core."""

from __future__ import annotations

import copy
import json
import unittest

from nanobot.agent.tools.insurance.planning_layer.prioritization import (
    PrioritizationInputError,
    PrioritizeFollowupsTool,
    prioritize_followups,
)


class PrioritizationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.payload = {
            "agent_id": "AGT001",
            "objective": {"open_gap": 100_000, "unit": "USD"},
            "constraints": {"top_k": 3},
            "candidates": [
                {
                    "candidate_id": "A",
                    "expected_contribution": 80_000,
                    "urgency": 0.4,
                    "actionability": 0.5,
                    "business_fit": 0.6,
                },
                {
                    "candidate_id": "B",
                    "expected_contribution": 60_000,
                    "urgency": 0.9,
                    "actionability": 0.9,
                    "business_fit": 0.9,
                },
                {
                    "candidate_id": "C",
                    "expected_contribution": 50_000,
                    "urgency": 0.8,
                    "actionability": 0.7,
                },
            ],
        }

    def test_scores_ranks_and_explains_top_k_deterministically(self) -> None:
        original = copy.deepcopy(self.payload)

        first = prioritize_followups(self.payload)
        second = prioritize_followups(self.payload)

        self.assertEqual(first, second)
        self.assertEqual(self.payload, original)
        self.assertEqual(
            [item["candidate_id"] for item in first["recommendations"]],
            ["B", "C", "A"],
        )
        self.assertEqual(first["recommendations"][0]["rank"], 1)
        self.assertEqual(first["recommendations"][0]["priority_level"], "P0")
        self.assertIn("score_components", first["recommendations"][0])
        self.assertEqual(
            first["recommendations"][1]["score_components"]["business_fit"]["normalised_value"],
            0.5,
        )

    def test_filters_ineligible_permission_compliance_invalid_and_duplicates(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["constraints"] = {"top_k": 10}
        payload["candidates"] = [
            payload["candidates"][0],
            {**payload["candidates"][0]},
            {"candidate_id": "I", "eligible": False},
            {"candidate_id": "P", "permission_allowed": False},
            {"candidate_id": "X", "compliance_allowed": False},
            {"candidate_id": "N", "expected_contribution": -1, "urgency": 0.5, "actionability": 0.5},
            {"candidate_id": "U", "expected_contribution": 1, "urgency": 1.2, "actionability": 0.5},
            "not-an-object",
        ]

        result = prioritize_followups(payload)

        self.assertEqual([item["candidate_id"] for item in result["recommendations"]], ["A"])
        self.assertEqual(
            [item["reason"] for item in result["excluded_candidates"]],
            [
                "duplicate_candidate_id",
                "ineligible",
                "permission_denied",
                "compliance_excluded",
                "invalid_expected_contribution",
                "invalid_urgency",
                "candidate_must_be_an_object",
            ],
        )

    def test_custom_weights_are_normalised_and_stable_ties_use_candidate_id(self) -> None:
        payload = {
            "agent_id": "AGT001",
            "objective": {"open_gap": 100},
            "weights": {
                "expected_contribution": 1,
                "urgency": 0,
                "actionability": 0,
                "business_fit": 0,
            },
            "candidates": [
                {"candidate_id": "B", "expected_contribution": 50, "urgency": 0.5, "actionability": 0.5},
                {"candidate_id": "A", "expected_contribution": 50, "urgency": 0.5, "actionability": 0.5},
            ],
        }

        result = prioritize_followups(payload)

        self.assertEqual([item["candidate_id"] for item in result["recommendations"]], ["A", "B"])
        self.assertEqual(result["weights"]["expected_contribution"], 1.0)

    def test_zero_gap_returns_no_recommendations(self) -> None:
        self.payload["objective"]["open_gap"] = 0

        result = prioritize_followups(self.payload)

        self.assertEqual(result["recommendations"], [])
        self.assertEqual(result["eligible_count"], 0)
        self.assertTrue(all(
            row["reason"] == "objective_already_met"
            for row in result["excluded_candidates"]
        ))

    def test_request_level_validation_rejects_unsafe_inputs(self) -> None:
        cases = [
            ({**self.payload, "agent_id": ""}, "agent_id"),
            ({**self.payload, "objective": {"open_gap": -1}}, "open_gap"),
            ({**self.payload, "candidates": {}}, "candidates"),
            ({**self.payload, "constraints": {"top_k": 0}}, "top_k"),
            ({**self.payload, "weights": {"unknown": 1}}, "Unknown score weights"),
        ]
        for payload, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                PrioritizationInputError, message
            ):
                prioritize_followups(payload)

    async def test_tool_exposes_contract_and_serialises_result(self) -> None:
        tool = PrioritizeFollowupsTool()

        result = json.loads(await tool.execute(**self.payload))

        self.assertEqual(tool.name, "prioritize_followups")
        self.assertEqual(result["agent_id"], "AGT001")
        self.assertEqual(tool.validate_params(tool.cast_params(self.payload)), [])

    def test_tool_contract_requires_candidate_scoring_fields(self) -> None:
        tool = PrioritizeFollowupsTool()
        required_fields = (
            "candidate_id",
            "expected_contribution",
            "urgency",
            "actionability",
        )

        for field in required_fields:
            payload = copy.deepcopy(self.payload)
            del payload["candidates"][0][field]

            with self.subTest(field=field):
                errors = tool.validate_params(tool.cast_params(payload))
                self.assertIn(f"missing required candidates[0].{field}", errors)

    def test_tool_contract_rejects_candidate_scores_outside_valid_ranges(self) -> None:
        tool = PrioritizeFollowupsTool()
        cases = (
            ("expected_contribution", -1, "must be >= 0"),
            ("urgency", -0.1, "must be >= 0"),
            ("urgency", 1.1, "must be <= 1"),
            ("actionability", 1.1, "must be <= 1"),
            ("business_fit", -0.1, "must be >= 0"),
        )

        for field, value, expected_error in cases:
            payload = copy.deepcopy(self.payload)
            payload["candidates"][0][field] = value

            with self.subTest(field=field, value=value):
                errors = tool.validate_params(tool.cast_params(payload))
                self.assertTrue(
                    any(
                        error.startswith(f"candidates[0].{field} ")
                        and expected_error in error
                        for error in errors
                    ),
                    errors,
                )


if __name__ == "__main__":
    unittest.main()
