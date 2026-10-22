"""Contract tests for the M2 coursework candidate dataset."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from nanobot.agent.tools.insurance.planning_layer.prioritization import (
    prioritize_followups,
)
from scripts.build_m2_candidate_dataset import build_dataset


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "evaluation" / "m2_candidate_scenarios.json"


class M2CandidateDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = json.loads(DATASET.read_text(encoding="utf-8"))

    def test_scope_and_currency_match_coursework_request(self) -> None:
        selection = self.dataset["selection"]
        self.assertEqual(selection["scenario_count"], 5)
        self.assertEqual(selection["candidate_count"], 40)
        self.assertEqual(selection["candidates_per_scenario"], 8)
        self.assertFalse(selection["random_sampling"])
        self.assertEqual(self.dataset["currency"], "USD")

        for scenario in self.dataset["scenarios"]:
            self.assertEqual(len(scenario["candidates"]), 8)
            self.assertEqual(scenario["objective"]["unit"], "USD")
            self.assertEqual(
                {row["candidate_type"] for row in scenario["candidates"]},
                {"policy", "client"},
            )
            self.assertEqual(
                sum(row["candidate_type"] == "policy" for row in scenario["candidates"]),
                4,
            )

    def test_checked_in_dataset_is_reproducible(self) -> None:
        self.assertEqual(build_dataset(), self.dataset)

    def test_candidate_contract_lineage_and_ranges(self) -> None:
        required = {
            "scenario_id", "agent_id", "candidate_id", "candidate_type",
            "premium", "currency", "expected_contribution", "policy_status",
            "submit_date", "estimated_approval_days", "client_tags",
            "product_type", "eligible", "permission_allowed",
            "compliance_allowed", "urgency", "actionability", "business_fit",
            "source_record_id", "source_path", "data_origin",
        }
        seen: set[str] = set()
        for scenario in self.dataset["scenarios"]:
            relevance = scenario["relevance"]
            for row in scenario["candidates"]:
                self.assertTrue(required <= row.keys())
                self.assertNotIn(row["candidate_id"], seen)
                seen.add(row["candidate_id"])
                self.assertEqual(row["currency"], "USD")
                self.assertGreaterEqual(row["premium"], 0)
                self.assertGreaterEqual(row["expected_contribution"], 0)
                for field in ("urgency", "actionability", "business_fit"):
                    self.assertGreaterEqual(row[field], 0)
                    self.assertLessEqual(row[field], 1)
                self.assertIsInstance(row["eligible"], bool)
                self.assertIsInstance(row["permission_allowed"], bool)
                self.assertIsInstance(row["compliance_allowed"], bool)
                self.assertIn(row["candidate_id"], relevance)
                self.assertIn(relevance[row["candidate_id"]], range(4))
                if row["candidate_type"] == "policy":
                    self.assertIsNotNone(row["policy_status"])
                    self.assertIsNotNone(row["submit_date"])
                    self.assertIsNotNone(row["estimated_approval_days"])
                else:
                    self.assertIsNone(row["policy_status"])
                    self.assertIn("not_applicable_reason", row)

    def test_every_scenario_is_accepted_by_m4_ranker(self) -> None:
        for scenario in self.dataset["scenarios"]:
            result = prioritize_followups({
                key: scenario[key]
                for key in ("agent_id", "objective", "constraints", "candidates")
            })
            self.assertEqual(result["candidate_count"], 8)
            self.assertEqual(result["eligible_count"], 8)
            self.assertEqual(len(result["recommendations"]), 5)
            self.assertEqual(result["excluded_candidates"], [])


if __name__ == "__main__":
    unittest.main()
