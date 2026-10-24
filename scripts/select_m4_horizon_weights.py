"""Select M4 horizon weights with scenario-level leave-one-out validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import fmean
from typing import Any, Mapping, Sequence

from nanobot.agent.tools.insurance.planning_layer.evaluation import (
    expected_contribution_baseline,
    ndcg_at_k,
    precision_at_k,
)
from nanobot.agent.tools.insurance.planning_layer.prioritization import (
    prioritize_followups,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCENARIOS = ROOT / "data/evaluation/m2_candidate_scenarios_v4.json"
DEFAULT_ANNOTATIONS = ROOT / "data/evaluation/m2_candidate_annotations_v4.json"
DEFAULT_OUTPUT = ROOT / "data/evaluation/m4_horizon_weight_selection_v3.json"
METRICS = ("precision_at_1", "ndcg_at_1", "precision_at_3", "ndcg_at_3")


def simplex_grid(
    units: int = 20, *, minimum_units: int = 1
) -> list[dict[str, float]]:
    """Return simplex points with a positive floor for every score factor."""
    if isinstance(units, bool) or not isinstance(units, int) or units <= 0:
        raise ValueError("units must be a positive integer")
    if (
        isinstance(minimum_units, bool)
        or not isinstance(minimum_units, int)
        or minimum_units <= 0
        or minimum_units * 4 > units
    ):
        raise ValueError("minimum_units must be positive and feasible for four factors")
    rows: list[dict[str, float]] = []
    upper = units - (3 * minimum_units)
    for contribution in range(minimum_units, upper + 1):
        for urgency in range(minimum_units, units - contribution - (2 * minimum_units) + 1):
            for actionability in range(
                minimum_units,
                units - contribution - urgency - minimum_units + 1,
            ):
                business_fit = units - contribution - urgency - actionability
                rows.append(
                    {
                        "expected_contribution": contribution / units,
                        "urgency": urgency / units,
                        "actionability": actionability / units,
                        "business_fit": business_fit / units,
                    }
                )
    return rows


def _index(rows: Any, label: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{label} scenarios must be a non-empty array")
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError(f"{label} scenario must be an object")
        scenario_id = row.get("scenario_id")
        if not isinstance(scenario_id, str) or not scenario_id or scenario_id in result:
            raise ValueError(f"{label} scenario IDs must be unique strings")
        result[scenario_id] = row
    return result


def _prepare(
    dataset: Mapping[str, Any], annotations: Mapping[str, Any]
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    if dataset.get("dataset_id") != "m2-coursework-candidates-v4":
        raise ValueError("The v4 horizon candidate dataset is required")
    if annotations.get("dataset_id") != dataset.get("dataset_id"):
        raise ValueError("Dataset IDs do not match")
    if annotations.get("annotation_status") != "complete":
        raise ValueError("Completed consensus annotations are required")
    scenarios = _index(dataset.get("scenarios"), "Candidate")
    labels = _index(annotations.get("scenarios"), "Annotation")
    if scenarios.keys() != labels.keys():
        raise ValueError("Candidate and annotation scenarios do not match")
    return scenarios, labels


def _metrics(
    scenario: Mapping[str, Any],
    annotation: Mapping[str, Any],
    weights: Mapping[str, float] | None,
) -> tuple[float, float, float, float]:
    relevance = annotation.get("consensus_relevance")
    formal_ids = annotation.get("ranking_candidate_ids")
    if not isinstance(relevance, Mapping) or not isinstance(formal_ids, list):
        raise ValueError("Formal candidates and consensus relevance are required")
    if set(relevance) != set(formal_ids):
        raise ValueError("Consensus relevance must cover the formal candidate set")
    numeric_relevance = {str(key): float(value) for key, value in relevance.items()}
    relevant_ids = {
        candidate_id for candidate_id, grade in numeric_relevance.items() if grade > 0
    }
    if weights is None:
        ranking = expected_contribution_baseline(
            scenario["candidates"], formal_ids
        )[:3]
    else:
        payload = {
            key: scenario[key]
            for key in ("agent_id", "objective", "constraints", "candidates")
        }
        payload["constraints"] = {**payload["constraints"], "top_k": 3}
        payload["weights"] = dict(weights)
        result = prioritize_followups(payload)
        ranking = [row["candidate_id"] for row in result["recommendations"]]
    return (
        precision_at_k(ranking, relevant_ids, 1),
        ndcg_at_k(ranking, numeric_relevance, 1),
        precision_at_k(ranking, relevant_ids, 3),
        ndcg_at_k(ranking, numeric_relevance, 3),
    )


def _mean(rows: Sequence[Sequence[float]]) -> tuple[float, ...]:
    return tuple(fmean(row[index] for row in rows) for index in range(len(METRICS)))


def _render(values: Sequence[float]) -> dict[str, float]:
    return {name: round(float(value), 6) for name, value in zip(METRICS, values)}


def select_horizon_weights(
    dataset: Mapping[str, Any],
    annotations: Mapping[str, Any],
    *,
    units: int = 20,
) -> dict[str, Any]:
    """Run deterministic leave-one-scenario-out constrained model selection."""
    scenarios, labels = _prepare(dataset, annotations)
    scenario_ids = sorted(scenarios)
    grid = simplex_grid(units)
    model_cache = {
        (scenario_id, index): _metrics(
            scenarios[scenario_id], labels[scenario_id], weights
        )
        for index, weights in enumerate(grid)
        for scenario_id in scenario_ids
    }
    baseline_cache = {
        scenario_id: _metrics(scenarios[scenario_id], labels[scenario_id], None)
        for scenario_id in scenario_ids
    }

    def choose(training_ids: Sequence[str]) -> tuple[int, tuple[float, ...], tuple[float, ...]]:
        baseline_mean = _mean([baseline_cache[sid] for sid in training_ids])
        accepted: list[tuple[tuple[float, ...], int]] = []
        for index, weights in enumerate(grid):
            model_mean = _mean([model_cache[(sid, index)] for sid in training_ids])
            if model_mean[0] + 1e-12 >= baseline_mean[0]:
                key = (
                    model_mean[3],
                    model_mean[1],
                    model_mean[0],
                    model_mean[2],
                    weights["expected_contribution"],
                    -weights["urgency"],
                    -weights["actionability"],
                    -weights["business_fit"],
                )
                accepted.append((key, index))
        if not accepted:
            raise ValueError("No positive-weight grid point preserves baseline Precision@1")
        selected = max(accepted)[1]
        return (
            selected,
            _mean([model_cache[(sid, selected)] for sid in training_ids]),
            baseline_mean,
        )

    folds: list[dict[str, Any]] = []
    held_out_model_rows: list[tuple[float, ...]] = []
    held_out_baseline_rows: list[tuple[float, ...]] = []
    for test_id in scenario_ids:
        training_ids = [sid for sid in scenario_ids if sid != test_id]
        selected, train_model, train_baseline = choose(training_ids)
        test_model = model_cache[(test_id, selected)]
        test_baseline = baseline_cache[test_id]
        held_out_model_rows.append(test_model)
        held_out_baseline_rows.append(test_baseline)
        folds.append(
            {
                "test_scenario_id": test_id,
                "training_scenario_ids": training_ids,
                "selected_weights": grid[selected],
                "training_model_metrics": _render(train_model),
                "training_baseline_metrics": _render(train_baseline),
                "test_model_metrics": _render(test_model),
                "test_baseline_metrics": _render(test_baseline),
            }
        )

    oof_model = _mean(held_out_model_rows)
    oof_baseline = _mean(held_out_baseline_rows)
    final_index, full_model, full_baseline = choose(scenario_ids)
    return {
        "selection_id": "m4-horizon-weight-selection-v3",
        "dataset_id": dataset.get("dataset_id"),
        "annotation_version": annotations.get("annotation_version"),
        "method": "Leave-one-scenario-out constrained grid selection",
        "scenario_count": len(scenario_ids),
        "grid": {
            "step": 1 / units,
            "candidate_weight_count": len(grid),
            "sum_constraint": 1.0,
            "minimum_weight": 1 / units,
            "all_factors_positive": True,
        },
        "selection_rule": (
            "Require every factor to carry at least 0.05 weight and require model "
            "Precision@1 on training scenarios to be no lower than the "
            "expected-contribution baseline; then maximise NDCG@3, followed by "
            "NDCG@1, Precision@1, Precision@3, higher contribution weight and "
            "deterministic remaining-weight order."
        ),
        "folds": folds,
        "out_of_fold": {
            "model": _render(oof_model),
            "baseline": _render(oof_baseline),
            "delta": _render(
                tuple(model - baseline for model, baseline in zip(oof_model, oof_baseline))
            ),
        },
        "selected_final_weights": grid[final_index],
        "all_scenario_metrics": {
            "model": _render(full_model),
            "baseline": _render(full_baseline),
            "delta": _render(
                tuple(model - baseline for model, baseline in zip(full_model, full_baseline))
            ),
        },
        "limitation": (
            "All ten available synthetic scenarios participate in model selection or "
            "held-out fold evaluation; no external holdout or production claim is made."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    dataset = json.loads(args.scenarios.read_text(encoding="utf-8"))
    annotations = json.loads(args.annotations.read_text(encoding="utf-8"))
    result = select_horizon_weights(dataset, annotations)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
