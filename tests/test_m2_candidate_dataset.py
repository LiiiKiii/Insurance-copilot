"""Contract tests for the M2 coursework candidate dataset."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from nanobot.agent.tools.insurance.planning_layer.prioritization import (
    prioritize_followups,
)
from scripts import build_m2_candidate_dataset as builder


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "evaluation" / "m2_candidate_scenarios.json"
BLIND_DATASET = ROOT / "data" / "evaluation" / "m2_candidate_blind.json"
ANNOTATIONS = ROOT / "data" / "evaluation" / "m2_candidate_annotations.json"


class M2CandidateDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = json.loads(DATASET.read_text(encoding="utf-8"))
        cls.blind = json.loads(BLIND_DATASET.read_text(encoding="utf-8"))
        cls.annotations = json.loads(ANNOTATIONS.read_text(encoding="utf-8"))

    def test_scope_and_currency_match_coursework_request(self) -> None:
        selection = self.dataset["selection"]
        self.assertEqual(selection["scenario_count"], 10)
        self.assertEqual(selection["candidate_count"], 100)
        self.assertEqual(selection["candidates_per_scenario"], 10)
        self.assertEqual(selection["filtered_candidate_count"], 60)
        self.assertFalse(selection["random_sampling"])
        self.assertEqual(self.dataset["currency"], "USD")
        self.assertEqual(self.dataset["evaluation_k"], [1, 3, 5])

        for scenario in self.dataset["scenarios"]:
            self.assertEqual(len(scenario["candidates"]), 10)
            self.assertEqual(scenario["objective"]["unit"], "USD")
            self.assertEqual(
                {row["candidate_type"] for row in scenario["candidates"]},
                {"policy", "client"},
            )
            self.assertEqual(
                sum(row["candidate_type"] == "policy" for row in scenario["candidates"]),
                4,
            )

    def test_checked_in_datasets_are_reproducible(self) -> None:
        generated = builder.build_dataset()
        self.assertEqual(generated, self.dataset)
        self.assertEqual(builder.build_blind_dataset(generated), self.blind)

    def test_candidate_contract_lineage_and_ranges(self) -> None:
        required = {
            "scenario_id", "agent_id", "candidate_id", "candidate_type",
            "premium", "currency", "expected_contribution", "policy_status",
            "submit_date", "estimated_approval_days", "client_tags",
            "product_type", "eligible", "permission_allowed",
            "compliance_allowed", "urgency", "actionability", "business_fit",
            "source_record_id", "source_path", "data_origin",
        }
        forbidden = {"reference_relevance_grade", "rule_based_provisional_grade"}
        seen: set[str] = set()
        for scenario in self.dataset["scenarios"]:
            self.assertNotIn("relevance", scenario)
            self.assertNotIn("consensus_relevance", scenario)
            for row in scenario["candidates"]:
                self.assertTrue(required <= row.keys())
                self.assertTrue(forbidden.isdisjoint(row))
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
            self.assertEqual(result["candidate_count"], 10)
            self.assertEqual(result["eligible_count"], 6)
            self.assertEqual(len(result["recommendations"]), 5)
            self.assertEqual(len(result["excluded_candidates"]), 4)
            self.assertEqual(
                {row["reason"] for row in result["excluded_candidates"]},
                {"ineligible"},
            )

    def test_blind_view_contains_only_evidence_for_eligible_candidates(self) -> None:
        allowed = {
            "candidate_id", "candidate_type", "premium", "currency",
            "policy_status", "submit_date", "estimated_approval_days",
            "client_tags", "product_type", "eligible", "permission_allowed",
            "compliance_allowed", "source_record_id",
        }
        forbidden = {
            "expected_contribution", "urgency", "actionability", "business_fit",
            "priority_score", "ranking", "baseline_ranking",
            "reference_relevance_grade", "rule_based_provisional_grade",
        }
        self.assertEqual(len(self.blind["scenarios"]), 10)
        for scenario in self.blind["scenarios"]:
            self.assertEqual(len(scenario["candidates"]), 6)
            for row in scenario["candidates"]:
                self.assertEqual(set(row), allowed)
                self.assertTrue(forbidden.isdisjoint(row))
                self.assertTrue(row["eligible"])
                self.assertTrue(row["permission_allowed"])
                self.assertTrue(row["compliance_allowed"])

    def test_annotation_template_is_separate_and_valid_when_completed(self) -> None:
        self.assertEqual(self.annotations["dataset_id"], self.dataset["dataset_id"])
        self.assertEqual(self.annotations["annotation_version"], "human-v1")
        self.assertIn(self.annotations["annotation_status"], {"pending", "complete"})
        blind_by_id = {
            row["scenario_id"]: {
                candidate["candidate_id"] for candidate in row["candidates"]
            }
            for row in self.blind["scenarios"]
        }
        self.assertEqual(len(self.annotations["scenarios"]), 10)
        for scenario in self.annotations["scenarios"]:
            expected_ids = blind_by_id[scenario["scenario_id"]]
            self.assertEqual(set(scenario["eligible_candidate_ids"]), expected_ids)
            self.assertGreaterEqual(len(scenario["annotations"]), 1)
            for annotation in scenario["annotations"]:
                ranking = annotation["ranking"]
                if ranking:
                    self.assertEqual(set(ranking), expected_ids)
                    self.assertEqual(len(ranking), 6)
            consensus = scenario["consensus_relevance"]
            if consensus:
                self.assertEqual(set(consensus), expected_ids)
                self.assertTrue(set(consensus.values()) <= {0, 1, 2, 3})
                self.assertTrue(set(consensus.values()) & {0, 1})
                self.assertTrue(set(consensus.values()) & {2, 3})
        if self.annotations["annotation_status"] == "complete":
            self.assertTrue(
                all(
                    row["consensus_relevance"]
                    for row in self.annotations["scenarios"]
                )
            )

        generator_source = Path(builder.__file__).read_text(encoding="utf-8")
        self.assertNotIn("m2_candidate_annotations.json", generator_source)


if __name__ == "__main__":
    unittest.main()
