"""Metric and fixed-fixture tests for the M4 ranking experiment."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from nanobot.agent.tools.insurance.planning_layer.evaluation import (
    evaluate_ranking,
    expected_contribution_baseline,
    ndcg_at_k,
    precision_at_k,
)
from nanobot.agent.tools.insurance.planning_layer.experiment import (
    ExperimentInputError,
    SENSITIVITY_PROFILES,
    evaluate_coursework_dataset,
)
from nanobot.agent.tools.insurance.planning_layer.prioritization import prioritize_followups


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT_ROOT / "data" / "evaluation" / "prioritization_synthetic.json"
SCENARIOS = PROJECT_ROOT / "data" / "evaluation" / "m2_candidate_scenarios.json"
ANNOTATIONS = PROJECT_ROOT / "data" / "evaluation" / "m2_candidate_annotations_v3.json"
HORIZON_SCENARIOS = (
    PROJECT_ROOT / "data" / "evaluation" / "m2_candidate_scenarios_v4.json"
)
HORIZON_ANNOTATIONS = (
    PROJECT_ROOT / "data" / "evaluation" / "m2_candidate_annotations_v4.json"
)


class PrioritizationEvaluationTests(unittest.TestCase):
    def test_precision_at_k_uses_binary_relevance(self) -> None:
        self.assertAlmostEqual(precision_at_k(["A", "B", "C"], {"A", "C"}, 3), 2 / 3)

    def test_ndcg_rewards_correct_graded_order(self) -> None:
        relevance = {"A": 3, "B": 2, "C": 1}

        self.assertAlmostEqual(ndcg_at_k(["A", "B", "C"], relevance, 3), 1.0)
        self.assertLess(ndcg_at_k(["C", "B", "A"], relevance, 3), 1.0)

    def test_metrics_reject_duplicate_rankings(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate"):
            precision_at_k(["A", "A"], {"A"}, 2)

    def test_fixed_synthetic_fixture_compares_proposed_with_baseline(self) -> None:
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        result = prioritize_followups({
            key: fixture[key]
            for key in ("agent_id", "objective", "constraints", "candidates")
        })
        proposed = [row["candidate_id"] for row in result["recommendations"]]
        baseline = expected_contribution_baseline(fixture["candidates"], proposed)
        metrics = evaluate_ranking(
            proposed,
            baseline,
            fixture["relevance"],
            fixture["evaluation_k"],
        )

        self.assertEqual(proposed, ["POL-B", "POL-C", "POL-D", "POL-A", "POL-E"])
        self.assertEqual(baseline, ["POL-E", "POL-A", "POL-C", "POL-B", "POL-D"])
        self.assertGreater(
            metrics["proposed"]["precision_at_k"],
            metrics["baseline"]["precision_at_k"],
        )
        self.assertGreater(
            metrics["proposed"]["ndcg_at_k"],
            metrics["baseline"]["ndcg_at_k"],
        )

    def test_complete_coursework_evaluation_covers_all_scenarios_and_k_values(self) -> None:
        dataset = json.loads(SCENARIOS.read_text(encoding="utf-8"))
        annotations = json.loads(ANNOTATIONS.read_text(encoding="utf-8"))

        result = evaluate_coursework_dataset(dataset, annotations)

        self.assertEqual(result["k_values"], [1, 3, 5])
        self.assertEqual(result["scenario_count"], 10)
        self.assertEqual(result["raw_candidate_count"], 100)
        self.assertEqual(result["eligible_candidate_count"], 60)
        self.assertEqual(len(result["scenarios"]), 10)
        self.assertEqual(result["annotation_agreement"]["ranking_pair_count"], 10)
        self.assertEqual(
            result["annotation_agreement"]["kendall_tau_a"]["mean"],
            0.173333,
        )
        self.assertEqual(
            result["feature_diagnostics"]["eligible_candidate_count"],
            60,
        )
        self.assertEqual(
            result["feature_diagnostics"]["normalised_components"]
            ["expected_contribution"]["mean"],
            0.01079,
        )
        self.assertEqual(
            result["feature_diagnostics"]["effective_weighted_points"]
            ["expected_contribution"]["mean"],
            0.431432,
        )
        self.assertEqual(
            result["aggregate"]["proposed"]["3"]["ndcg_at_k"]["mean"],
            0.948759,
        )
        self.assertEqual(
            result["aggregate"]["baseline"]["3"]["ndcg_at_k"]["mean"],
            0.596313,
        )
        self.assertEqual(
            result["aggregate"]["proposed"]["5"]["ndcg_at_k"]["mean"],
            0.978259,
        )
        self.assertEqual(
            {row["profile"] for row in result["sensitivity"]["profiles"]},
            set(SENSITIVITY_PROFILES),
        )
        for row in result["scenarios"]:
            self.assertEqual(len(row["proposed_ranking"]), 5)
            self.assertEqual(len(row["baseline_ranking"]), 5)
            self.assertEqual(set(row["metrics"]), {"1", "3", "5"})
        for ranking_name in ("proposed", "baseline"):
            for k in ("1", "3", "5"):
                for metric in ("precision_at_k", "ndcg_at_k"):
                    summary = result["aggregate"][ranking_name][k][metric]
                    self.assertGreaterEqual(summary["mean"], 0)
                    self.assertLessEqual(summary["mean"], 1)
                    self.assertGreaterEqual(summary["population_std"], 0)
        for profile in result["sensitivity"]["profiles"]:
            overlap = profile["top_max_k_overlap_with_default"]
            self.assertGreaterEqual(overlap["mean"], 0)
            self.assertLessEqual(overlap["mean"], 1)

    def test_coursework_evaluation_rejects_pending_consensus(self) -> None:
        dataset = json.loads(SCENARIOS.read_text(encoding="utf-8"))
        annotations = json.loads(ANNOTATIONS.read_text(encoding="utf-8"))
        annotations["annotation_status"] = "pending"

        with self.assertRaisesRegex(ExperimentInputError, "complete"):
            evaluate_coursework_dataset(dataset, annotations)

    def test_horizon_evaluation_reports_unsupported_k_without_padding(self) -> None:
        dataset = json.loads(HORIZON_SCENARIOS.read_text(encoding="utf-8"))
        annotations = json.loads(HORIZON_ANNOTATIONS.read_text(encoding="utf-8"))
        annotations = copy.deepcopy(annotations)
        annotations["annotation_status"] = "complete"
        for scenario in annotations["scenarios"]:
            ranking = scenario["ranking_candidate_ids"]
            for annotation in scenario["annotations"]:
                annotation["ranking"] = list(ranking)
            scenario["consensus_relevance"] = {
                candidate_id: len(ranking) - index
                for index, candidate_id in enumerate(ranking)
            }

        result = evaluate_coursework_dataset(dataset, annotations)

        self.assertEqual(result["evaluation_id"], "m4-coursework-evaluation-v4")
        self.assertEqual(result["requested_k_values"], [1, 3, 5])
        self.assertEqual(result["k_values"], [1, 3])
        self.assertEqual(result["unavailable_k"][0]["k"], 5)
        self.assertEqual(
            result["unavailable_k"][0]["minimum_formal_candidate_count"], 3
        )
        self.assertEqual(result["eligible_candidate_count"], 37)
        self.assertEqual(
            result["annotation_provenance"]["consensus_protocol"],
            "m2-v4-consensus-v1",
        )
        self.assertEqual(
            result["annotation_provenance"]["annotators"],
            [
                "non_m4_annotator_1",
                "non_m4_annotator_2",
                "non_m4_annotator_3",
            ],
        )
        self.assertEqual(
            result["feature_diagnostics"]["expected_contribution_normalisation"],
            "min(expected_contribution / objective.horizon_open_gap, 1)",
        )
        self.assertNotIn("5", result["aggregate"]["proposed"])
        self.assertTrue(all(
            len(row["proposed_ranking"]) <= 4 for row in result["scenarios"]
        ))

    def test_completed_horizon_consensus_produces_frozen_final_metrics(self) -> None:
        dataset = json.loads(HORIZON_SCENARIOS.read_text(encoding="utf-8"))
        annotations = json.loads(HORIZON_ANNOTATIONS.read_text(encoding="utf-8"))

        result = evaluate_coursework_dataset(dataset, annotations)

        self.assertEqual(result["annotation_status"], "complete")
        self.assertEqual(result["annotation_agreement"]["ranking_pair_count"], 30)
        self.assertEqual(
            result["annotation_agreement"]["kendall_tau_a"]["mean"], 0.555556
        )
        self.assertEqual(
            result["annotation_agreement"]["spearman_rho"]["mean"], 0.666667
        )
        self.assertEqual(
            result["aggregate"]["proposed"]["1"]["precision_at_k"]["mean"],
            1.0,
        )
        self.assertEqual(
            result["aggregate"]["proposed"]["3"]["ndcg_at_k"]["mean"],
            0.907364,
        )
        self.assertEqual(
            result["aggregate"]["baseline"]["3"]["ndcg_at_k"]["mean"],
            0.876069,
        )
        self.assertGreater(
            result["aggregate"]["delta"]["3"]["ndcg_at_k"]["mean"], 0
        )
        self.assertLess(
            result["aggregate"]["delta"]["3"]["precision_at_k"]["mean"], 0
        )


if __name__ == "__main__":
    unittest.main()
