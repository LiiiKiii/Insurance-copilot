"""Deterministic contract tests for competition gap analysis."""

import unittest

from nanobot.agent.tools.insurance.reasoning_layer.gap_analysis import (
    compute_gap_analysis,
)


def competition(
    competition_id: str,
    gap: float | None,
    **overrides: object,
) -> dict:
    """Create a minimal competition input with deterministic defaults."""
    result = {
        "id": competition_id,
        "name": competition_id,
        "gap": gap,
        "unit": "HKD",
        "days_remaining": 10,
        "tags": [],
    }
    result.update(overrides)
    return result


class ComputeGapAnalysisTests(unittest.TestCase):
    def test_zero_gap_is_achieved(self) -> None:
        result = compute_gap_analysis([competition("zero", 0)], 0)[0]

        self.assertEqual(result["actual_gap"], 0)
        self.assertEqual(result["pending_deduction"], 0)
        self.assertEqual(result["pending_coverage_pct"], 100.0)
        self.assertEqual(result["status"], "achieved")

    def test_negative_gap_is_treated_as_achieved(self) -> None:
        result = compute_gap_analysis([competition("negative", -1000)], 0)[0]

        self.assertEqual(result["actual_gap"], 0)
        self.assertEqual(result["pending_deduction"], 0)
        self.assertEqual(result["pending_coverage_pct"], 100.0)
        self.assertEqual(result["status"], "achieved")

    def test_zero_pending_keeps_hkd_gap_open(self) -> None:
        result = compute_gap_analysis([competition("open", 50000)], 0)[0]

        self.assertEqual(result["actual_gap"], 50000)
        self.assertEqual(result["pending_deduction"], 0)
        self.assertEqual(result["status"], "open")

    def test_pending_less_than_gap_needs_new_business(self) -> None:
        result = compute_gap_analysis([competition("partial", 50000)], 20000)[0]

        self.assertEqual(result["actual_gap"], 30000)
        self.assertEqual(result["pending_deduction"], 20000)
        self.assertEqual(result["pending_coverage_pct"], 40.0)
        self.assertEqual(result["status"], "needs_new_business")

    def test_pending_equal_to_gap_covers_gap(self) -> None:
        result = compute_gap_analysis([competition("covered", 50000)], 50000)[0]

        self.assertEqual(result["actual_gap"], 0)
        self.assertEqual(result["pending_deduction"], 50000)
        self.assertEqual(result["pending_coverage_pct"], 100.0)
        self.assertEqual(result["status"], "covered_by_pending")

    def test_pending_greater_than_gap_only_deducts_gap(self) -> None:
        result = compute_gap_analysis([competition("covered", 50000)], 60000)[0]

        self.assertEqual(result["actual_gap"], 0)
        self.assertEqual(result["pending_deduction"], 50000)
        self.assertEqual(result["status"], "covered_by_pending")

    def test_exact_half_coverage_is_partially_covered(self) -> None:
        result = compute_gap_analysis([competition("half", 100000)], 50000)[0]

        self.assertEqual(result["pending_coverage_pct"], 50.0)
        self.assertEqual(result["status"], "partially_covered")

    def test_non_hkd_gap_does_not_use_pending_premium(self) -> None:
        result = compute_gap_analysis(
            [competition("count", 5, unit="policies")],
            100000,
        )[0]

        self.assertEqual(result["actual_gap"], 5)
        self.assertEqual(result["pending_deduction"], 0)
        self.assertEqual(result["pending_coverage_pct"], 0.0)
        self.assertEqual(result["status"], "open")

    def test_missing_unit_defaults_to_hkd(self) -> None:
        item = competition("default-unit", 50000)
        del item["unit"]

        result = compute_gap_analysis([item], 20000)[0]

        self.assertEqual(result["unit"], "HKD")
        self.assertEqual(result["pending_deduction"], 20000)
        self.assertEqual(result["actual_gap"], 30000)

    def test_missing_tags_defaults_to_empty_list(self) -> None:
        item = competition("default-tags", 50000)
        del item["tags"]

        result = compute_gap_analysis([item], 0)[0]

        self.assertEqual(result["tags"], [])

    def test_none_gap_is_achieved(self) -> None:
        result = compute_gap_analysis([competition("none", None)], 50000)[0]

        self.assertEqual(result["actual_gap"], 0)
        self.assertEqual(result["pending_deduction"], 0)
        self.assertEqual(result["pending_coverage_pct"], 100.0)
        self.assertEqual(result["status"], "achieved")

    def test_shared_pending_pool_is_not_double_counted(self) -> None:
        result = compute_gap_analysis(
            [
                competition("A", 60000, days_remaining=5),
                competition("B", 80000, days_remaining=20),
            ],
            100000,
        )

        self.assertEqual(result[0]["pending_deduction"], 60000)
        self.assertEqual(result[0]["actual_gap"], 0)
        self.assertEqual(result[1]["pending_deduction"], 40000)
        self.assertEqual(result[1]["actual_gap"], 40000)
        self.assertEqual(
            sum(item["pending_deduction"] for item in result),
            100000,
        )

    def test_allocation_order_differs_from_return_order(self) -> None:
        result = compute_gap_analysis(
            [
                competition("B", 80000, days_remaining=20),
                competition("A", 60000, days_remaining=5),
            ],
            100000,
        )

        self.assertEqual([item["competition_id"] for item in result], ["B", "A"])
        self.assertEqual(result[0]["pending_deduction"], 40000)
        self.assertEqual(result[0]["actual_gap"], 40000)
        self.assertEqual(result[1]["pending_deduction"], 60000)
        self.assertEqual(result[1]["actual_gap"], 0)

    def test_same_deadline_uses_stable_input_order(self) -> None:
        result = compute_gap_analysis(
            [
                competition("A", 40000, days_remaining=5),
                competition("B", 40000, days_remaining=5),
            ],
            50000,
        )

        self.assertEqual(result[0]["pending_deduction"], 40000)
        self.assertEqual(result[1]["pending_deduction"], 10000)

    def test_missing_days_remaining_has_lowest_priority(self) -> None:
        result = compute_gap_analysis(
            [
                competition("A", 50000, days_remaining=None),
                competition("B", 50000, days_remaining=3),
            ],
            60000,
        )

        self.assertEqual([item["competition_id"] for item in result], ["A", "B"])
        self.assertEqual(result[0]["pending_deduction"], 10000)
        self.assertEqual(result[1]["pending_deduction"], 50000)

    def test_empty_competitions_returns_empty_list(self) -> None:
        self.assertEqual(compute_gap_analysis([], 100000), [])


if __name__ == "__main__":
    unittest.main()
