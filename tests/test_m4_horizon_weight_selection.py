"""Tests for deterministic M4 horizon weight selection."""

import json
from pathlib import Path

import pytest

from scripts.select_m4_horizon_weights import select_horizon_weights, simplex_grid


ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "data/evaluation/m2_candidate_scenarios_v4.json"
ANNOTATIONS = ROOT / "data/evaluation/m2_candidate_annotations_v4.json"


def test_simplex_grid_is_complete_and_deterministic():
    grid = simplex_grid(20)

    assert len(grid) == 969
    assert all(sum(row.values()) == pytest.approx(1) for row in grid)
    assert all(min(row.values()) >= 0.05 for row in grid)
    assert grid == simplex_grid(20)


def test_simplex_grid_rejects_a_non_positive_or_infeasible_floor():
    with pytest.raises(ValueError, match="minimum_units"):
        simplex_grid(20, minimum_units=0)
    with pytest.raises(ValueError, match="minimum_units"):
        simplex_grid(3, minimum_units=1)


def test_leave_one_out_selection_and_metrics_are_reproducible():
    dataset = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    annotations = json.loads(ANNOTATIONS.read_text(encoding="utf-8"))

    result = select_horizon_weights(dataset, annotations)

    expected = {
        "expected_contribution": 0.2,
        "urgency": 0.4,
        "actionability": 0.35,
        "business_fit": 0.05,
    }
    assert result["selected_final_weights"] == expected
    assert len(result["folds"]) == 10
    assert all(
        min(fold["selected_weights"].values()) >= 0.05
        for fold in result["folds"]
    )
    assert result["out_of_fold"]["model"] == {
        "precision_at_1": 1.0,
        "ndcg_at_1": 0.733333,
        "precision_at_3": 0.666667,
        "ndcg_at_3": 0.837984,
    }
    assert result["out_of_fold"]["baseline"]["ndcg_at_3"] == 0.876069
    assert result["out_of_fold"]["delta"]["ndcg_at_1"] == 0.066667
    assert result["all_scenario_metrics"]["model"]["ndcg_at_3"] == 0.907364


def test_selection_requires_completed_matching_inputs():
    dataset = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    annotations = json.loads(ANNOTATIONS.read_text(encoding="utf-8"))
    annotations["annotation_status"] = "pending"

    with pytest.raises(ValueError, match="Completed"):
        select_horizon_weights(dataset, annotations)
