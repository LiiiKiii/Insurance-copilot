"""Focused regression tests for the attribution-gap compatibility module."""

from nanobot.agent.tools.insurance.reasoning_layer.attribution_gap import (
    compute_attribution_gap,
)


def test_supports_all_existing_snapshot_formats() -> None:
    dimensions = {
        "key_metrics": {
            "dimensions": [
                {"name": "Premium", "current": 80, "peer_avg": 100, "unit": "HKD"},
            ]
        },
        "lead_followup": {
            "label": "Lead follow-up",
            "data": {"new_lead_response_hours": 48},
            "peer_avg": {"new_lead_response_hours": 24},
        },
        "training": {
            "label": "Training",
            "metrics": {
                "sessions": {"value": 2, "peer_avg": 5, "label": "Sessions"},
            },
        },
    }

    gaps = compute_attribution_gap(dimensions)

    assert {item["metric"] for item in gaps} == {
        "Premium",
        "new_lead_response_hours",
        "sessions",
    }
    assert all(item["is_weakness"] for item in gaps)


def test_filters_small_invalid_and_zero_baseline_values() -> None:
    dimensions = {
        "activity": {
            "data": {
                "small_gap": 98,
                "zero_baseline": 10,
                "nested_value": {"count": 10},
            },
            "peer_avg": {
                "small_gap": 100,
                "zero_baseline": 0,
                "nested_value": 5,
            },
        }
    }

    assert compute_attribution_gap(dimensions) == []


def test_orders_weaknesses_by_magnitude_before_strengths() -> None:
    dimensions = {
        "key_metrics": {
            "dimensions": [
                {"name": "Strength", "current": 150, "peer_avg": 100},
                {"name": "Smaller weakness", "current": 80, "peer_avg": 100},
                {"name": "Larger weakness", "current": 50, "peer_avg": 100},
            ]
        }
    }

    gaps = compute_attribution_gap(dimensions)

    assert [item["metric"] for item in gaps] == [
        "Larger weakness",
        "Smaller weakness",
        "Strength",
    ]


def test_boundary_gap_is_reported_but_not_misclassified_as_weakness() -> None:
    dimensions = {
        "key_metrics": {
            "dimensions": [
                {"name": "Boundary", "current": 95, "peer_avg": 100},
            ]
        }
    }

    gaps = compute_attribution_gap(dimensions)

    assert len(gaps) == 1
    assert gaps[0]["gap_pct"] == -5.0
    assert gaps[0]["is_weakness"] is False
