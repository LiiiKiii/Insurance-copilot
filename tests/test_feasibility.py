"""Deterministic contract tests for feasibility calculations."""

import unittest

from nanobot.agent.tools.insurance.reasoning_layer.feasibility import (
    compute_feasibility,
)


class ComputeFeasibilityTests(unittest.TestCase):
    def test_achieved_gap_returns_achieved_contract(self) -> None:
        result = compute_feasibility(
            actual_gap=0,
            days_remaining=60,
            monthly_avg=50000,
            unit="HKD",
        )

        self.assertEqual(result["level"], "achieved")
        self.assertEqual(result["level_label"], "Achieved")
        self.assertEqual(result["probability_pct"], 100)
        self.assertEqual(result["daily_needed"], 0)
        self.assertNotIn("required_ratio", result)

    def test_negative_gap_is_treated_as_achieved(self) -> None:
        result = compute_feasibility(
            actual_gap=-1000,
            days_remaining=60,
            monthly_avg=50000,
            unit="HKD",
        )

        self.assertEqual(result["level"], "achieved")
        self.assertEqual(result["probability_pct"], 100)

    def test_clearly_high_feasibility_hkd(self) -> None:
        result = compute_feasibility(
            actual_gap=10000,
            days_remaining=60,
            monthly_avg=50000,
            unit="HKD",
        )

        self.assertEqual(result["level"], "high")
        self.assertAlmostEqual(result["required_ratio"], 0.1)
        self.assertEqual(result["probability_pct"], 89)

    def test_zero_days_hkd_has_very_low_feasibility(self) -> None:
        result = compute_feasibility(
            actual_gap=50000,
            days_remaining=0,
            monthly_avg=50000,
            unit="HKD",
        )

        self.assertEqual(result["level"], "very_low")
        self.assertEqual(result["probability_pct"], 5)
        self.assertEqual(result["daily_needed"], float("inf"))
        self.assertEqual(result["required_ratio"], float("inf"))

    def test_negative_days_hkd_has_very_low_feasibility(self) -> None:
        result = compute_feasibility(
            actual_gap=50000,
            days_remaining=-1,
            monthly_avg=50000,
            unit="HKD",
        )

        self.assertEqual(result["level"], "very_low")
        self.assertEqual(result["probability_pct"], 5)

    def test_zero_monthly_capacity_hkd_has_very_low_feasibility(self) -> None:
        result = compute_feasibility(
            actual_gap=50000,
            days_remaining=60,
            monthly_avg=0,
            unit="HKD",
        )

        self.assertEqual(result["level"], "very_low")
        self.assertEqual(result["probability_pct"], 5)
        self.assertEqual(result["required_ratio"], float("inf"))

    def test_negative_monthly_capacity_hkd_has_very_low_feasibility(self) -> None:
        result = compute_feasibility(
            actual_gap=50000,
            days_remaining=60,
            monthly_avg=-1000,
            unit="HKD",
        )

        self.assertEqual(result["level"], "very_low")
        self.assertEqual(result["probability_pct"], 5)

    def test_hkd_high_threshold_is_inclusive(self) -> None:
        result = compute_feasibility(
            actual_gap=1000,
            days_remaining=10,
            monthly_avg=3000,
            unit="HKD",
        )

        self.assertEqual(result["level"], "high")
        self.assertEqual(result["required_ratio"], 1.0)
        self.assertEqual(result["probability_pct"], 80)

    def test_hkd_medium_threshold_is_inclusive(self) -> None:
        result = compute_feasibility(
            actual_gap=1500,
            days_remaining=10,
            monthly_avg=3000,
            unit="HKD",
        )

        self.assertEqual(result["level"], "medium")
        self.assertEqual(result["required_ratio"], 1.5)
        self.assertEqual(result["probability_pct"], 50)

    def test_hkd_low_threshold_is_inclusive(self) -> None:
        result = compute_feasibility(
            actual_gap=2500,
            days_remaining=10,
            monthly_avg=3000,
            unit="HKD",
        )

        self.assertEqual(result["level"], "low")
        self.assertEqual(result["required_ratio"], 2.5)
        self.assertEqual(result["probability_pct"], 20)

    def test_hkd_ratio_above_low_threshold_is_very_low(self) -> None:
        result = compute_feasibility(
            actual_gap=3000,
            days_remaining=10,
            monthly_avg=3000,
            unit="HKD",
        )

        self.assertEqual(result["level"], "very_low")

    def test_hkd_very_large_ratio_respects_probability_floor(self) -> None:
        result = compute_feasibility(
            actual_gap=1000000,
            days_remaining=10,
            monthly_avg=1,
            unit="HKD",
        )

        self.assertEqual(result["level"], "very_low")
        self.assertEqual(result["probability_pct"], 5)

    def test_non_hkd_high_threshold_is_inclusive(self) -> None:
        result = compute_feasibility(
            actual_gap=3,
            days_remaining=7,
            monthly_avg=0,
            unit="policies",
        )

        self.assertEqual(result["level"], "high")
        self.assertEqual(result["required_ratio"], 1.0)
        self.assertEqual(result["probability_pct"], 80)

    def test_non_hkd_medium_threshold_is_inclusive(self) -> None:
        result = compute_feasibility(
            actual_gap=6,
            days_remaining=7,
            monthly_avg=0,
            unit="policies",
        )

        self.assertEqual(result["level"], "medium")
        self.assertEqual(result["required_ratio"], 2.0)
        self.assertEqual(result["probability_pct"], 50)

    def test_non_hkd_low_threshold_is_inclusive(self) -> None:
        result = compute_feasibility(
            actual_gap=10.5,
            days_remaining=7,
            monthly_avg=0,
            unit="policies",
        )

        self.assertEqual(result["level"], "low")
        self.assertEqual(result["required_ratio"], 3.5)

    def test_non_hkd_ratio_above_low_threshold_is_very_low(self) -> None:
        result = compute_feasibility(
            actual_gap=12,
            days_remaining=7,
            monthly_avg=0,
            unit="policies",
        )

        self.assertEqual(result["level"], "very_low")

    def test_non_hkd_result_is_independent_of_monthly_average(self) -> None:
        without_monthly_capacity = compute_feasibility(
            actual_gap=10,
            days_remaining=60,
            monthly_avg=0,
            unit="policies",
        )
        with_monthly_capacity = compute_feasibility(
            actual_gap=10,
            days_remaining=60,
            monthly_avg=99999999,
            unit="policies",
        )

        self.assertEqual(without_monthly_capacity, with_monthly_capacity)

    def test_non_achieved_output_has_exact_keys(self) -> None:
        result = compute_feasibility(
            actual_gap=10000,
            days_remaining=60,
            monthly_avg=50000,
            unit="HKD",
        )

        self.assertEqual(
            set(result),
            {
                "level",
                "level_label",
                "probability_pct",
                "daily_needed",
                "required_ratio",
                "narrative",
            },
        )

    def test_feasibility_level_labels(self) -> None:
        cases = [
            (1000, "high", "High feasibility"),
            (1500, "medium", "Medium feasibility"),
            (2500, "low", "Low feasibility"),
            (3000, "very_low", "Very low feasibility"),
        ]

        for actual_gap, level, label in cases:
            with self.subTest(actual_gap=actual_gap):
                result = compute_feasibility(
                    actual_gap=actual_gap,
                    days_remaining=10,
                    monthly_avg=3000,
                    unit="HKD",
                )
                self.assertEqual(result["level"], level)
                self.assertEqual(result["level_label"], label)


if __name__ == "__main__":
    unittest.main()
