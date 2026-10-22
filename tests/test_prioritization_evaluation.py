"""Metric and fixed-fixture tests for the M4 ranking experiment."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from nanobot.agent.tools.insurance.planning_layer.evaluation import (
    evaluate_ranking,
    expected_contribution_baseline,
    ndcg_at_k,
    precision_at_k,
)
from nanobot.agent.tools.insurance.planning_layer.prioritization import prioritize_followups


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT_ROOT / "data" / "evaluation" / "prioritization_synthetic.json"


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


if __name__ == "__main__":
    unittest.main()
