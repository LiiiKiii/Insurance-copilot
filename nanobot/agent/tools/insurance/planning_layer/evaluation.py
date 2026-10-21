"""Offline ranking metrics for the M4 prioritisation experiment."""

from __future__ import annotations

import math
from typing import Iterable, Mapping, Sequence


def _validate_ranking(ranking: Sequence[str], k: int) -> None:
    if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
        raise ValueError("k must be a positive integer.")
    if len(set(ranking)) != len(ranking):
        raise ValueError("ranking must not contain duplicate identifiers.")


def precision_at_k(ranking: Sequence[str], relevant_ids: Iterable[str], k: int) -> float:
    """Return binary Precision@K, using K as the denominator."""
    _validate_ranking(ranking, k)
    relevant = set(relevant_ids)
    hits = sum(1 for candidate_id in ranking[:k] if candidate_id in relevant)
    return hits / k


def ndcg_at_k(ranking: Sequence[str], relevance: Mapping[str, float], k: int) -> float:
    """Return graded NDCG@K with exponential gain and log2 discount."""
    _validate_ranking(ranking, k)
    if any(value < 0 or not math.isfinite(float(value)) for value in relevance.values()):
        raise ValueError("relevance values must be finite and non-negative.")

    def dcg(values: Sequence[float]) -> float:
        return sum(
            (2 ** float(value) - 1) / math.log2(index + 2)
            for index, value in enumerate(values[:k])
        )

    observed = dcg([float(relevance.get(candidate_id, 0)) for candidate_id in ranking])
    ideal = dcg(sorted((float(value) for value in relevance.values()), reverse=True))
    return observed / ideal if ideal > 0 else 0.0


def expected_contribution_baseline(
    candidates: Sequence[Mapping[str, object]], eligible_ids: Iterable[str]
) -> list[str]:
    """Rank the eligible candidate set by expected contribution only."""
    allowed = set(eligible_ids)
    rows = [row for row in candidates if row.get("candidate_id") in allowed]
    return [
        str(row["candidate_id"])
        for row in sorted(
            rows,
            key=lambda row: (
                -float(row.get("expected_contribution", 0)),
                str(row["candidate_id"]),
            ),
        )
    ]


def evaluate_ranking(
    proposed_ranking: Sequence[str],
    baseline_ranking: Sequence[str],
    relevance: Mapping[str, float],
    k: int,
) -> dict[str, object]:
    """Compare the proposed ranking with a fixed baseline at the same K."""
    relevant_ids = {candidate_id for candidate_id, grade in relevance.items() if grade > 0}
    return {
        "k": k,
        "proposed": {
            "precision_at_k": round(precision_at_k(proposed_ranking, relevant_ids, k), 6),
            "ndcg_at_k": round(ndcg_at_k(proposed_ranking, relevance, k), 6),
        },
        "baseline": {
            "precision_at_k": round(precision_at_k(baseline_ranking, relevant_ids, k), 6),
            "ndcg_at_k": round(ndcg_at_k(baseline_ranking, relevance, k), 6),
        },
    }
