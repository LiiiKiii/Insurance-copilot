"""Reproducible multi-scenario evaluation for the M4 prioritisation model."""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from itertools import combinations
from typing import Any

from nanobot.agent.tools.insurance.planning_layer.evaluation import (
    evaluate_ranking,
    expected_contribution_baseline,
)
from nanobot.agent.tools.insurance.planning_layer.prioritization import (
    DEFAULT_WEIGHTS,
    prioritize_followups,
)


DEFAULT_K_VALUES = (1, 3, 5)
SENSITIVITY_PROFILES: dict[str, dict[str, float]] = {
    "balanced": {
        "expected_contribution": 0.25,
        "urgency": 0.25,
        "actionability": 0.25,
        "business_fit": 0.25,
    },
    "contribution_heavy": {
        "expected_contribution": 0.70,
        "urgency": 0.10,
        "actionability": 0.10,
        "business_fit": 0.10,
    },
    "urgency_heavy": {
        "expected_contribution": 0.20,
        "urgency": 0.50,
        "actionability": 0.20,
        "business_fit": 0.10,
    },
    "actionability_heavy": {
        "expected_contribution": 0.20,
        "urgency": 0.20,
        "actionability": 0.50,
        "business_fit": 0.10,
    },
    "business_fit_heavy": {
        "expected_contribution": 0.20,
        "urgency": 0.15,
        "actionability": 0.15,
        "business_fit": 0.50,
    },
}


class ExperimentInputError(ValueError):
    """Raised when the candidate or annotation dataset is incomplete."""


def _validate_k_values(k_values: Sequence[int]) -> tuple[int, ...]:
    values = tuple(k_values)
    if (
        not values
        or any(isinstance(k, bool) or not isinstance(k, int) or k <= 0 for k in values)
        or len(set(values)) != len(values)
    ):
        raise ExperimentInputError("K values must be distinct positive integers.")
    return values


def _scenario_maps(
    dataset: Mapping[str, Any], annotations: Mapping[str, Any]
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    if dataset.get("dataset_id") != annotations.get("dataset_id"):
        raise ExperimentInputError("Candidate and annotation dataset IDs do not match.")
    if annotations.get("annotation_status") != "complete":
        raise ExperimentInputError("Consensus annotations must be complete.")

    candidate_rows = dataset.get("scenarios")
    annotation_rows = annotations.get("scenarios")
    if not isinstance(candidate_rows, list) or not isinstance(annotation_rows, list):
        raise ExperimentInputError("Both inputs must contain scenario arrays.")

    def index(rows: list[Any], label: str) -> dict[str, Mapping[str, Any]]:
        result: dict[str, Mapping[str, Any]] = {}
        for row in rows:
            if not isinstance(row, Mapping):
                raise ExperimentInputError(f"{label} scenario must be an object.")
            scenario_id = row.get("scenario_id")
            if not isinstance(scenario_id, str) or not scenario_id or scenario_id in result:
                raise ExperimentInputError(f"{label} scenario IDs must be unique strings.")
            result[scenario_id] = row
        return result

    candidates_by_id = index(candidate_rows, "Candidate")
    annotations_by_id = index(annotation_rows, "Annotation")
    if candidates_by_id.keys() != annotations_by_id.keys():
        raise ExperimentInputError("Candidate and annotation scenarios do not match.")
    if not candidates_by_id:
        raise ExperimentInputError("At least one scenario is required.")
    return candidates_by_id, annotations_by_id


def _validated_relevance(
    scenario: Mapping[str, Any], annotation: Mapping[str, Any], max_k: int
) -> dict[str, float]:
    candidates = scenario.get("candidates")
    eligible_ids = annotation.get(
        "ranking_candidate_ids", annotation.get("eligible_candidate_ids")
    )
    relevance = annotation.get("consensus_relevance")
    if not isinstance(candidates, list):
        raise ExperimentInputError("Scenario candidates must be an array.")
    if not isinstance(eligible_ids, list) or len(set(eligible_ids)) != len(eligible_ids):
        raise ExperimentInputError("Eligible candidate IDs must be a unique array.")
    if len(eligible_ids) < max_k:
        raise ExperimentInputError("Each scenario must contain at least max(K) candidates.")
    if not isinstance(relevance, Mapping) or set(relevance) != set(eligible_ids):
        raise ExperimentInputError("Consensus relevance must cover every eligible candidate.")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value < 0
        for value in relevance.values()
    ):
        raise ExperimentInputError("Consensus relevance grades must be finite and non-negative.")

    candidate_ids = {
        row.get("candidate_id") for row in candidates if isinstance(row, Mapping)
    }
    if not set(eligible_ids) <= candidate_ids:
        raise ExperimentInputError("An eligible candidate is absent from the scenario input.")
    return {str(candidate_id): float(value) for candidate_id, value in relevance.items()}


def _summary(values: Sequence[float]) -> dict[str, float]:
    return {
        "mean": round(statistics.fmean(values), 6),
        "population_std": round(statistics.pstdev(values), 6),
    }


def _distribution_summary(values: Sequence[float]) -> dict[str, float]:
    if not values:
        raise ExperimentInputError("A diagnostic distribution cannot be empty.")
    return {
        "min": round(min(values), 6),
        "mean": round(statistics.fmean(values), 6),
        "max": round(max(values), 6),
        "population_std": round(statistics.pstdev(values), 6),
    }


def _feature_diagnostics(
    candidates_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Describe the effective feature scale without changing ranking behaviour."""
    raw_expected: list[float] = []
    open_gaps: list[float] = []
    normalised: dict[str, list[float]] = {name: [] for name in DEFAULT_WEIGHTS}
    weighted_points: dict[str, list[float]] = {name: [] for name in DEFAULT_WEIGHTS}

    for scenario_id in sorted(candidates_by_id):
        scenario = candidates_by_id[scenario_id]
        payload = {
            key: scenario[key]
            for key in ("agent_id", "objective", "constraints", "candidates")
        }
        payload["constraints"] = {**payload["constraints"], "top_k": 50}
        result = prioritize_followups(payload)
        objective = scenario["objective"]
        gap_field = (
            "horizon_open_gap" if "horizon_open_gap" in objective else "open_gap"
        )
        gap = float(objective[gap_field])
        open_gaps.append(gap)
        for recommendation in result["recommendations"]:
            raw_expected.append(float(recommendation["expected_contribution"]))
            for name in DEFAULT_WEIGHTS:
                component = recommendation["score_components"][name]
                normalised[name].append(float(component["normalised_value"]))
                weighted_points[name].append(float(component["weighted_points"]))

    horizon_mode = all(
        "horizon_open_gap" in scenario.get("objective", {})
        for scenario in candidates_by_id.values()
    )
    gap_field = "horizon_open_gap" if horizon_mode else "open_gap"
    return {
        "eligible_candidate_count": len(raw_expected),
        "expected_contribution_normalisation": (
            f"min(expected_contribution / objective.{gap_field}, 1)"
        ),
        f"objective_{gap_field}": _distribution_summary(open_gaps),
        "raw_expected_contribution": _distribution_summary(raw_expected),
        "normalised_components": {
            name: _distribution_summary(values)
            for name, values in normalised.items()
        },
        "effective_weighted_points": {
            name: _distribution_summary(values)
            for name, values in weighted_points.items()
        },
        "interpretation": (
            "Diagnostics describe the committed dataset and default scorer only; "
            "they are not used to tune weights or transform evaluation labels."
        ),
    }


def _rank_correlations(
    left: Sequence[str], right: Sequence[str]
) -> tuple[float, float]:
    """Return Kendall tau-a and Spearman rho for two complete permutations."""
    left_position = {candidate_id: index for index, candidate_id in enumerate(left)}
    right_position = {candidate_id: index for index, candidate_id in enumerate(right)}
    concordant = 0
    discordant = 0
    for first, second in combinations(left, 2):
        product = (
            (left_position[first] - left_position[second])
            * (right_position[first] - right_position[second])
        )
        if product > 0:
            concordant += 1
        else:
            discordant += 1
    pair_count = concordant + discordant
    kendall = (concordant - discordant) / pair_count if pair_count else 0.0

    size = len(left)
    squared_rank_distance = sum(
        (left_position[candidate_id] - right_position[candidate_id]) ** 2
        for candidate_id in left
    )
    spearman = (
        1 - (6 * squared_rank_distance) / (size * (size**2 - 1))
        if size > 1
        else 1.0
    )
    return kendall, spearman


def _annotation_agreement(
    annotations_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    kendall_values: list[float] = []
    spearman_values: list[float] = []
    same_top_values: list[float] = []
    top_three_overlap_values: list[float] = []
    scenario_pair_count = 0

    for scenario_id in sorted(annotations_by_id):
        scenario = annotations_by_id[scenario_id]
        eligible_ids = scenario.get(
            "ranking_candidate_ids", scenario.get("eligible_candidate_ids")
        )
        annotation_rows = scenario.get("annotations")
        if not isinstance(eligible_ids, list) or not isinstance(annotation_rows, list):
            raise ExperimentInputError("Annotation rankings are unavailable.")
        rankings: list[list[str]] = []
        for annotation in annotation_rows:
            ranking = annotation.get("ranking") if isinstance(annotation, Mapping) else None
            if (
                not isinstance(ranking, list)
                or len(ranking) != len(eligible_ids)
                or len(set(ranking)) != len(ranking)
                or set(ranking) != set(eligible_ids)
            ):
                raise ExperimentInputError(
                    f"Annotation ranking is incomplete in scenario {scenario_id}."
                )
            rankings.append(ranking)
        if len(rankings) < 2:
            raise ExperimentInputError(
                f"At least two annotations are required in scenario {scenario_id}."
            )

        for left, right in combinations(rankings, 2):
            kendall, spearman = _rank_correlations(left, right)
            kendall_values.append(kendall)
            spearman_values.append(spearman)
            same_top_values.append(float(left[0] == right[0]))
            overlap_k = min(3, len(left))
            top_three_overlap_values.append(
                len(set(left[:overlap_k]) & set(right[:overlap_k])) / overlap_k
            )
            scenario_pair_count += 1

    return {
        "ranking_pair_count": scenario_pair_count,
        "kendall_tau_a": _summary(kendall_values),
        "spearman_rho": _summary(spearman_values),
        "same_top_1_rate": _summary(same_top_values),
        "top_3_overlap_rate": _summary(top_three_overlap_values),
    }


def _aggregate(
    scenarios: Sequence[Mapping[str, Any]], k_values: Sequence[int]
) -> dict[str, dict[str, dict[str, dict[str, float]]]]:
    result: dict[str, dict[str, dict[str, dict[str, float]]]] = {
        "proposed": {},
        "baseline": {},
        "delta": {},
    }
    for k in k_values:
        key = str(k)
        for ranking_name in ("proposed", "baseline"):
            result[ranking_name][key] = {
                metric: _summary(
                    [
                        float(row["metrics"][key][ranking_name][metric])
                        for row in scenarios
                    ]
                )
                for metric in ("precision_at_k", "ndcg_at_k")
            }
        result["delta"][key] = {
            metric: _summary(
                [
                    float(row["metrics"][key]["proposed"][metric])
                    - float(row["metrics"][key]["baseline"][metric])
                    for row in scenarios
                ]
            )
            for metric in ("precision_at_k", "ndcg_at_k")
        }
    return result


def _evaluate_scenarios(
    candidates_by_id: Mapping[str, Mapping[str, Any]],
    annotations_by_id: Mapping[str, Mapping[str, Any]],
    k_values: Sequence[int],
    weights: Mapping[str, float] | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    max_k = max(k_values)
    for scenario_id in sorted(candidates_by_id):
        scenario = candidates_by_id[scenario_id]
        annotation = annotations_by_id[scenario_id]
        relevance = _validated_relevance(scenario, annotation, max_k)
        payload = {
            key: scenario[key]
            for key in ("agent_id", "objective", "constraints", "candidates")
        }
        payload["constraints"] = {**payload["constraints"], "top_k": max_k}
        if weights is not None:
            payload["weights"] = dict(weights)
        ranking = prioritize_followups(payload)
        proposed = [row["candidate_id"] for row in ranking["recommendations"]]
        eligible_ids = annotation.get(
            "ranking_candidate_ids", annotation["eligible_candidate_ids"]
        )
        baseline = expected_contribution_baseline(scenario["candidates"], eligible_ids)
        if ranking["eligible_count"] != len(eligible_ids):
            raise ExperimentInputError(
                f"Eligible count mismatch in scenario {scenario_id}."
            )
        rows.append(
            {
                "scenario_id": scenario_id,
                "agent_id": scenario["agent_id"],
                "eligible_candidate_count": len(eligible_ids),
                "proposed_ranking": proposed,
                "baseline_ranking": baseline[:max_k],
                "metrics": {
                    str(k): evaluate_ranking(proposed, baseline, relevance, k)
                    for k in k_values
                },
            }
        )
    return rows


def evaluate_coursework_dataset(
    dataset: Mapping[str, Any],
    annotations: Mapping[str, Any],
    *,
    k_values: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Evaluate default M4 weights, baseline, and fixed sensitivity profiles."""
    candidates_by_id, annotations_by_id = _scenario_maps(dataset, annotations)
    requested_ks = _validate_k_values(
        k_values
        if k_values is not None
        else dataset.get("evaluation_k", DEFAULT_K_VALUES)
    )
    ranking_candidate_counts = {
        scenario_id: len(
            annotation.get(
                "ranking_candidate_ids",
                annotation.get("eligible_candidate_ids", []),
            )
        )
        for scenario_id, annotation in annotations_by_id.items()
    }
    minimum_candidate_count = min(ranking_candidate_counts.values())
    ks = tuple(k for k in requested_ks if k <= minimum_candidate_count)
    unavailable_k = [
        {
            "k": k,
            "status": "not_applicable",
            "reason": (
                "At least one scenario has fewer than K formal ranking candidates; "
                "out-of-horizon candidates are not used as padding."
            ),
            "minimum_formal_candidate_count": minimum_candidate_count,
        }
        for k in requested_ks
        if k > minimum_candidate_count
    ]
    if not ks:
        raise ExperimentInputError(
            "No requested K is supported by every scenario's formal candidate set."
        )
    default_rows = _evaluate_scenarios(
        candidates_by_id, annotations_by_id, ks, DEFAULT_WEIGHTS
    )
    default_aggregate = _aggregate(default_rows, ks)

    sensitivity: list[dict[str, Any]] = []
    for name, weights in SENSITIVITY_PROFILES.items():
        rows = _evaluate_scenarios(
            candidates_by_id, annotations_by_id, ks, weights
        )
        aggregate = _aggregate(rows, ks)["proposed"]
        overlap = _summary(
            [
                len(
                    set(row["proposed_ranking"][: max(ks)])
                    & set(default_row["proposed_ranking"][: max(ks)])
                )
                / max(ks)
                for row, default_row in zip(rows, default_rows, strict=True)
            ]
        )
        sensitivity.append(
            {
                "profile": name,
                "weights": weights,
                "aggregate": aggregate,
                "top_max_k_overlap_with_default": overlap,
                "mean_ndcg_at_max_k_delta_from_default": round(
                    aggregate[str(max(ks))]["ndcg_at_k"]["mean"]
                    - default_aggregate["proposed"][str(max(ks))]["ndcg_at_k"]["mean"],
                    6,
                ),
            }
        )

    adjudication = annotations.get("adjudication")
    provenance = (
        {
            key: adjudication.get(key)
            for key in ("method", "adjudicator", "limitation", "independence")
            if adjudication.get(key) is not None
        }
        if isinstance(adjudication, Mapping)
        else {}
    )
    return {
        "evaluation_id": (
            "m4-coursework-evaluation-v2"
            if "horizon_open_gap"
            in next(iter(candidates_by_id.values())).get("objective", {})
            else "m4-coursework-evaluation-v1"
        ),
        "dataset_id": dataset.get("dataset_id"),
        "annotation_version": annotations.get("annotation_version"),
        "annotation_status": annotations.get("annotation_status"),
        "annotation_provenance": provenance,
        "annotation_agreement": _annotation_agreement(annotations_by_id),
        "feature_diagnostics": _feature_diagnostics(candidates_by_id),
        "requested_k_values": list(requested_ks),
        "k_values": list(ks),
        "unavailable_k": unavailable_k,
        "formal_candidate_counts": ranking_candidate_counts,
        "scenario_count": len(default_rows),
        "raw_candidate_count": sum(
            len(row.get("candidates", [])) for row in candidates_by_id.values()
        ),
        "eligible_candidate_count": sum(
            row["eligible_candidate_count"] for row in default_rows
        ),
        "default_weights": DEFAULT_WEIGHTS,
        "aggregate": default_aggregate,
        "scenarios": default_rows,
        "sensitivity": {
            "design": (
                "Fixed one-factor stress profiles plus an equal-weight profile; "
                "the default weights are not selected from evaluation labels."
            ),
            "profiles": sensitivity,
        },
    }
