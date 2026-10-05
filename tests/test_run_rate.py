"""Deterministic contract tests for annual run-rate calculations."""

import unittest

from nanobot.agent.tools.insurance.reasoning_layer.run_rate import (
    compute_run_rate,
)


PERIOD_START = "2026-01-01"
AS_OF_DATE = "2026-09-01"


class ComputeRunRateTests(unittest.TestCase):
    def test_normal_deterministic_calculation(self) -> None:
        result = compute_run_rate(
            current=600000,
            target=1200000,
            period_start=PERIOD_START,
            as_of_date=AS_OF_DATE,
        )

        self.assertEqual(result["months_elapsed"], 8.0)
        self.assertEqual(result["months_remaining"], 4.0)
        self.assertEqual(result["monthly_avg"], 75160)
        self.assertEqual(result["monthly_needed"], 149362)
        self.assertEqual(result["projected_year_end"], 901924)
        self.assertEqual(result["projected_rate"], 0.752)
        self.assertEqual(result["pace_status"], "at_risk")
        self.assertIn("149,362 per month", result["narrative"])

    def test_already_achieved_target(self) -> None:
        result = compute_run_rate(
            current=1200000,
            target=1000000,
            period_start=PERIOD_START,
            as_of_date=AS_OF_DATE,
        )

        self.assertEqual(result["monthly_needed"], 0)
        self.assertEqual(result["pace_status"], "on_track")
        self.assertEqual(result["narrative"], "Target already achieved.")

    def test_current_equal_to_target_is_achieved(self) -> None:
        result = compute_run_rate(
            current=1000000,
            target=1000000,
            period_start=PERIOD_START,
            as_of_date=AS_OF_DATE,
        )

        self.assertEqual(result["monthly_needed"], 0)
        self.assertEqual(result["pace_status"], "on_track")
        self.assertIn("achieved", result["narrative"].lower())

    def test_zero_current_is_critical(self) -> None:
        result = compute_run_rate(
            current=0,
            target=1000000,
            period_start=PERIOD_START,
            as_of_date=AS_OF_DATE,
        )

        self.assertEqual(result["monthly_avg"], 0)
        self.assertEqual(result["projected_year_end"], 0)
        self.assertEqual(result["projected_rate"], 0)
        self.assertEqual(result["pace_status"], "critical")
        self.assertGreater(result["monthly_needed"], 0)

    def test_zero_target_raises_value_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "^target must be greater than zero$"):
            compute_run_rate(1, 0, as_of_date=AS_OF_DATE)

    def test_negative_target_raises_value_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "^target must be greater than zero$"):
            compute_run_rate(1, -1, as_of_date=AS_OF_DATE)

    def test_same_day_start_uses_elapsed_floor(self) -> None:
        result = compute_run_rate(
            current=100,
            target=1000,
            period_start=AS_OF_DATE,
            as_of_date=AS_OF_DATE,
        )

        self.assertEqual(result["months_elapsed"], 0.5)
        self.assertEqual(result["months_remaining"], 11.5)

    def test_future_start_uses_elapsed_floor(self) -> None:
        result = compute_run_rate(
            current=100,
            target=1000,
            period_start="2026-10-01",
            as_of_date=AS_OF_DATE,
        )

        self.assertEqual(result["months_elapsed"], 0.5)
        self.assertEqual(result["months_remaining"], 11.5)

    def test_period_longer_than_twelve_months_uses_remaining_floor(self) -> None:
        result = compute_run_rate(
            current=100,
            target=1000,
            period_start="2025-01-01",
            as_of_date=AS_OF_DATE,
        )

        self.assertEqual(result["months_remaining"], 0.5)

    def test_default_period_start_uses_as_of_year_january_first(self) -> None:
        default_start = compute_run_rate(
            current=600000,
            target=1200000,
            as_of_date=AS_OF_DATE,
        )
        explicit_start = compute_run_rate(
            current=600000,
            target=1200000,
            period_start=PERIOD_START,
            as_of_date=AS_OF_DATE,
        )

        self.assertEqual(default_start, explicit_start)

    def test_invalid_period_start_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            compute_run_rate(
                current=1,
                target=2,
                period_start="not-a-date",
                as_of_date=AS_OF_DATE,
            )

    def test_invalid_as_of_date_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            compute_run_rate(
                current=1,
                target=2,
                period_start=PERIOD_START,
                as_of_date="not-a-date",
            )

    def test_output_contract_has_exact_keys(self) -> None:
        result = compute_run_rate(
            current=600000,
            target=1200000,
            period_start=PERIOD_START,
            as_of_date=AS_OF_DATE,
        )

        self.assertEqual(
            set(result),
            {
                "current",
                "target",
                "months_elapsed",
                "months_remaining",
                "monthly_avg",
                "monthly_needed",
                "projected_year_end",
                "projected_rate",
                "pace_status",
                "pace_label",
                "narrative",
            },
        )

    def test_pace_statuses_have_consistent_labels(self) -> None:
        cases = [
            (800000, "on_track", "On track"),
            (600000, "behind", "Behind pace"),
            (500000, "at_risk", "At risk"),
            (300000, "critical", "Critical pace gap"),
        ]

        for current, status, label in cases:
            with self.subTest(current=current):
                result = compute_run_rate(
                    current=current,
                    target=1000000,
                    period_start=PERIOD_START,
                    as_of_date=AS_OF_DATE,
                )
                self.assertEqual(result["pace_status"], status)
                self.assertEqual(result["pace_label"], label)


if __name__ == "__main__":
    unittest.main()
