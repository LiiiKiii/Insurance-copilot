"""Deterministic candidate prioritisation for M4 follow-up planning.

The scorer is deliberately data-source independent.  M2 or an API adapter
supplies verified candidate records; this module only filters, scores, ranks,
and explains them.  It does not query the database or override authoritative
gap, permission, or compliance decisions.
"""

from __future__ import annotations

import json
import math
from typing import Any

from nanobot.agent.tools.base import Tool


RANKING_VERSION = "m4-weighted-v1"
DEFAULT_WEIGHTS = {
    "expected_contribution": 0.40,
    "urgency": 0.25,
    "actionability": 0.20,
    "business_fit": 0.15,
}
_OPTIONAL_DEFAULTS = {"business_fit": 0.5}
_REQUIRED_SCORE_FIELDS = ("expected_contribution", "urgency", "actionability")


class PrioritizationInputError(ValueError):
    """Raised when request-level prioritisation inputs are invalid."""


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _normalise_weights(overrides: dict[str, Any] | None) -> dict[str, float]:
    raw: dict[str, Any] = dict(DEFAULT_WEIGHTS)
    if overrides:
        unknown = set(overrides) - set(DEFAULT_WEIGHTS)
        if unknown:
            raise PrioritizationInputError(
                f"Unknown score weights: {', '.join(sorted(unknown))}"
            )
        raw.update(overrides)

    weights: dict[str, float] = {}
    for name, value in raw.items():
        number = _finite_number(value)
        if number is None or number < 0:
            raise PrioritizationInputError(
                f"Weight {name} must be a finite non-negative number."
            )
        weights[name] = number

    total = sum(weights.values())
    if total <= 0:
        raise PrioritizationInputError("At least one score weight must be positive.")
    return {name: value / total for name, value in weights.items()}


def _priority_level(score: float) -> str:
    if score >= 75:
        return "P0"
    if score >= 50:
        return "P1"
    return "P2"


def _exclusion_reason(candidate: Any, seen_ids: set[str]) -> tuple[str | None, str | None]:
    if not isinstance(candidate, dict):
        return None, "candidate_must_be_an_object"

    raw_id = candidate.get("candidate_id")
    if not isinstance(raw_id, str) or not raw_id.strip():
        return None, "missing_candidate_id"
    candidate_id = raw_id.strip()
    if candidate_id in seen_ids:
        return candidate_id, "duplicate_candidate_id"
    seen_ids.add(candidate_id)

    if candidate.get("eligible", True) is not True:
        return candidate_id, "ineligible"
    if candidate.get("permission_allowed", True) is not True:
        return candidate_id, "permission_denied"
    if candidate.get("compliance_allowed", True) is not True:
        return candidate_id, "compliance_excluded"

    expected = _finite_number(candidate.get("expected_contribution"))
    if expected is None or expected < 0:
        return candidate_id, "invalid_expected_contribution"
    for field in ("urgency", "actionability"):
        value = _finite_number(candidate.get(field))
        if value is None or not 0 <= value <= 1:
            return candidate_id, f"invalid_{field}"
    business_fit = _finite_number(
        candidate.get("business_fit", _OPTIONAL_DEFAULTS["business_fit"])
    )
    if business_fit is None or not 0 <= business_fit <= 1:
        return candidate_id, "invalid_business_fit"
    return candidate_id, None


def prioritize_followups(payload: dict[str, Any]) -> dict[str, Any]:
    """Filter and rank follow-up candidates with an explainable weighted score."""
    if not isinstance(payload, dict):
        raise PrioritizationInputError("Prioritisation input must be an object.")

    agent_id = payload.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id.strip():
        raise PrioritizationInputError("agent_id is required.")

    objective = payload.get("objective")
    if not isinstance(objective, dict):
        raise PrioritizationInputError("objective must be an object.")
    open_gap = _finite_number(objective.get("open_gap"))
    if open_gap is None or open_gap < 0:
        raise PrioritizationInputError("objective.open_gap must be non-negative.")

    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise PrioritizationInputError("candidates must be an array.")

    constraints = payload.get("constraints") or {}
    if not isinstance(constraints, dict):
        raise PrioritizationInputError("constraints must be an object.")
    top_k = constraints.get("top_k", 5)
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 50:
        raise PrioritizationInputError("constraints.top_k must be an integer from 1 to 50.")

    weights = _normalise_weights(payload.get("weights"))
    excluded: list[dict[str, str]] = []
    eligible: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    if open_gap == 0:
        for candidate in candidates:
            candidate_id = candidate.get("candidate_id") if isinstance(candidate, dict) else None
            excluded.append({
                "candidate_id": candidate_id if isinstance(candidate_id, str) else "",
                "reason": "objective_already_met",
            })
        return {
            "agent_id": agent_id.strip(),
            "objective": dict(objective),
            "ranking_version": RANKING_VERSION,
            "weights": weights,
            "recommendations": [],
            "excluded_candidates": excluded,
            "eligible_count": 0,
            "candidate_count": len(candidates),
        }

    for index, candidate in enumerate(candidates):
        candidate_id, reason = _exclusion_reason(candidate, seen_ids)
        if reason:
            excluded.append({
                "candidate_id": candidate_id or f"input[{index}]",
                "reason": reason,
            })
            continue

        assert candidate_id is not None
        expected = float(candidate["expected_contribution"])
        urgency = float(candidate["urgency"])
        actionability = float(candidate["actionability"])
        business_fit = float(
            candidate.get("business_fit", _OPTIONAL_DEFAULTS["business_fit"])
        )
        components = {
            "expected_contribution": min(expected / open_gap, 1.0),
            "urgency": urgency,
            "actionability": actionability,
            "business_fit": business_fit,
        }
        weighted_components = {
            name: round(100 * components[name] * weights[name], 4)
            for name in DEFAULT_WEIGHTS
        }
        score = round(sum(weighted_components.values()), 4)
        eligible.append({
            "candidate_id": candidate_id,
            "expected_contribution": expected,
            "urgency": urgency,
            "priority_score": score,
            "score_components": {
                name: {
                    "normalised_value": round(components[name], 4),
                    "weight": round(weights[name], 4),
                    "weighted_points": weighted_components[name],
                }
                for name in DEFAULT_WEIGHTS
            },
            "evidence": candidate.get("evidence", {}),
            "requested_action": candidate.get("recommended_action"),
        })

    eligible.sort(
        key=lambda item: (
            -item["priority_score"],
            -item["urgency"],
            -item["expected_contribution"],
            item["candidate_id"],
        )
    )

    recommendations: list[dict[str, Any]] = []
    for rank, item in enumerate(eligible[:top_k], start=1):
        level = _priority_level(item["priority_score"])
        timing = "today" if level == "P0" else "within 3 days" if level == "P1" else "this week"
        action = item.pop("requested_action") or f"Follow up with {item['candidate_id']} {timing}."
        recommendations.append({
            **item,
            "rank": rank,
            "priority_level": level,
            "recommended_action": action,
            "recommended_timing": timing,
            "ranking_reason": (
                f"Ranked #{rank} with score {item['priority_score']:.2f}; "
                f"expected contribution {item['expected_contribution']:.2f}, "
                f"urgency {item['urgency']:.2f}."
            ),
        })

    return {
        "agent_id": agent_id.strip(),
        "objective": dict(objective),
        "ranking_version": RANKING_VERSION,
        "weights": {name: round(value, 4) for name, value in weights.items()},
        "recommendations": recommendations,
        "excluded_candidates": excluded,
        "eligible_count": len(eligible),
        "candidate_count": len(candidates),
    }


class PrioritizeFollowupsTool(Tool):
    """Expose deterministic M4 prioritisation through the generic tool contract."""

    @property
    def name(self) -> str:
        return "prioritize_followups"

    @property
    def description(self) -> str:
        return (
            "Rank verified customer or policy follow-up candidates using an "
            "explainable deterministic score and return Top-K recommendations."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "minLength": 1},
                "objective": {
                    "type": "object",
                    "properties": {"open_gap": {"type": "number", "minimum": 0}},
                    "required": ["open_gap"],
                },
                "candidates": {"type": "array", "items": {"type": "object"}},
                "constraints": {"type": "object"},
                "weights": {"type": "object"},
            },
            "required": ["agent_id", "objective", "candidates"],
        }

    async def execute(self, **kwargs: Any) -> str:
        return json.dumps(prioritize_followups(kwargs), ensure_ascii=False)
