"""Deterministic candidate prioritisation for M4 follow-up planning.

The scorer is deliberately data-source independent.  M2 or an API adapter
supplies verified candidate records; this module only filters, scores, ranks,
and explains them.  It does not query the database or override authoritative
gap, permission, or compliance decisions.
"""

from __future__ import annotations

import json
import math
from datetime import date
from typing import Any

from nanobot.agent.tools.base import Tool


RANKING_VERSION = "m4-weighted-v1"
HORIZON_RANKING_VERSION = "m4-horizon-weighted-v4"
DEFAULT_WEIGHTS = {
    "expected_contribution": 0.40,
    "urgency": 0.25,
    "actionability": 0.20,
    "business_fit": 0.15,
}
HORIZON_DEFAULT_WEIGHTS = {
    "expected_contribution": 0.20,
    "urgency": 0.40,
    "actionability": 0.35,
    "business_fit": 0.05,
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


def _normalise_weights(
    overrides: dict[str, Any] | None,
    defaults: dict[str, float] = DEFAULT_WEIGHTS,
) -> dict[str, float]:
    raw: dict[str, Any] = dict(defaults)
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


def _iso_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _objective_gap(objective: dict[str, Any]) -> tuple[float, str, bool]:
    """Resolve the declared denominator without an annual-gap fallback."""
    horizon_fields = {
        "planning_horizon_start",
        "planning_horizon_end",
        "horizon_target",
        "horizon_current",
        "horizon_open_gap",
    }
    horizon_mode = bool(horizon_fields & objective.keys())
    if horizon_mode:
        missing = sorted(horizon_fields - objective.keys())
        if missing:
            raise PrioritizationInputError(
                "Horizon objective is incomplete; missing: " + ", ".join(missing)
            )
        gap = _finite_number(objective.get("horizon_open_gap"))
        if gap is None or gap < 0:
            raise PrioritizationInputError(
                "objective.horizon_open_gap must be non-negative."
            )
        start = _iso_date(objective.get("planning_horizon_start"))
        end = _iso_date(objective.get("planning_horizon_end"))
        if start is None or end is None or end < start:
            raise PrioritizationInputError(
                "objective planning horizon must contain valid inclusive ISO dates."
            )
        target = _finite_number(objective.get("horizon_target"))
        current = _finite_number(objective.get("horizon_current"))
        if target is None or current is None or target < 0 or current < 0:
            raise PrioritizationInputError(
                "objective horizon target and current values must be non-negative."
            )
        expected_gap = max(target - current, 0.0)
        if not math.isclose(gap, expected_gap, rel_tol=0, abs_tol=0.005):
            raise PrioritizationInputError(
                "objective.horizon_open_gap must equal max(horizon_target - "
                "horizon_current, 0)."
            )
        metric = objective.get("metric")
        unit = objective.get("unit")
        if not isinstance(metric, str) or not metric.strip():
            raise PrioritizationInputError("objective.metric is required in horizon mode.")
        if not isinstance(unit, str) or not unit.strip():
            raise PrioritizationInputError("objective.unit is required in horizon mode.")
        return gap, "horizon_open_gap", True

    gap = _finite_number(objective.get("open_gap"))
    if gap is None or gap < 0:
        raise PrioritizationInputError("objective.open_gap must be non-negative.")
    return gap, "open_gap", False


def _exclusion_reason(
    candidate: Any,
    seen_ids: set[str],
    *,
    objective: dict[str, Any],
    horizon_mode: bool,
) -> tuple[str | None, str | None]:
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

    if horizon_mode:
        if candidate.get("horizon_ranking_eligible") is not True:
            return candidate_id, "not_horizon_ranking_eligible"
        if candidate.get("within_planning_horizon") is not True:
            return candidate_id, "outside_planning_horizon"
        if candidate.get("metric") != objective.get("metric"):
            return candidate_id, "objective_metric_mismatch"
        if candidate.get("currency") != objective.get("unit"):
            return candidate_id, "objective_unit_mismatch"
        realization = _iso_date(candidate.get("expected_realization_date"))
        start = _iso_date(objective.get("planning_horizon_start"))
        end = _iso_date(objective.get("planning_horizon_end"))
        if realization is None:
            return candidate_id, "missing_expected_realization_date"
        assert start is not None and end is not None
        if not start <= realization <= end:
            return candidate_id, "expected_realization_outside_horizon"

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
    normalisation_gap, denominator_field, horizon_mode = _objective_gap(objective)

    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise PrioritizationInputError("candidates must be an array.")

    constraints = payload.get("constraints") or {}
    if not isinstance(constraints, dict):
        raise PrioritizationInputError("constraints must be an object.")
    top_k = constraints.get("top_k", 5)
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 50:
        raise PrioritizationInputError("constraints.top_k must be an integer from 1 to 50.")

    weights = _normalise_weights(
        payload.get("weights"),
        HORIZON_DEFAULT_WEIGHTS if horizon_mode else DEFAULT_WEIGHTS,
    )
    excluded: list[dict[str, str]] = []
    eligible: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    ranking_version = HORIZON_RANKING_VERSION if horizon_mode else RANKING_VERSION
    if normalisation_gap == 0:
        for candidate in candidates:
            candidate_id = candidate.get("candidate_id") if isinstance(candidate, dict) else None
            excluded.append({
                "candidate_id": candidate_id if isinstance(candidate_id, str) else "",
                "reason": "objective_already_met",
            })
        return {
            "agent_id": agent_id.strip(),
            "objective": dict(objective),
            "ranking_version": ranking_version,
            "normalization_denominator": {
                "field": denominator_field,
                "value": normalisation_gap,
                "annual_gap_fallback": False,
            },
            "weights": weights,
            "recommendations": [],
            "excluded_candidates": excluded,
            "eligible_count": 0,
            "candidate_count": len(candidates),
        }

    for index, candidate in enumerate(candidates):
        candidate_id, reason = _exclusion_reason(
            candidate,
            seen_ids,
            objective=objective,
            horizon_mode=horizon_mode,
        )
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
            "expected_contribution": min(expected / normalisation_gap, 1.0),
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
        "ranking_version": ranking_version,
        "normalization_denominator": {
            "field": denominator_field,
            "value": normalisation_gap,
            "annual_gap_fallback": False,
        },
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
                    "description": (
                        "Use open_gap for the legacy annual-gap contract, or the "
                        "complete horizon fields for formal short-horizon ranking."
                    ),
                    "properties": {
                        "open_gap": {"type": "number", "minimum": 0},
                        "metric": {"type": "string", "minLength": 1},
                        "unit": {"type": "string", "minLength": 1},
                        "planning_horizon_start": {"type": "string", "minLength": 10},
                        "planning_horizon_end": {"type": "string", "minLength": 10},
                        "horizon_target": {"type": "number", "minimum": 0},
                        "horizon_current": {"type": "number", "minimum": 0},
                        "horizon_open_gap": {"type": "number", "minimum": 0},
                    },
                },
                "candidates": {
                    "type": "array",
                    "description": (
                        "Verified follow-up candidates. Scores must be supplied "
                        "by an authoritative data or preparation tool, not guessed."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "candidate_id": {
                                "type": "string",
                                "minLength": 1,
                                "description": (
                                    "Stable customer or policy identifier."
                                ),
                            },
                            "expected_contribution": {
                                "type": "number",
                                "minimum": 0,
                                "description": (
                                    "Non-negative expected contribution in the "
                                    "same metric, unit, and crediting period as "
                                    "the selected objective gap."
                                ),
                            },
                            "urgency": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                                "description": "Normalised urgency score from 0 to 1.",
                            },
                            "actionability": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                                "description": (
                                    "Normalised actionability score from 0 to 1."
                                ),
                            },
                            "business_fit": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                                "description": (
                                    "Optional normalised business-fit score; "
                                    "defaults to 0.5 when omitted."
                                ),
                            },
                            "eligible": {"type": "boolean"},
                            "permission_allowed": {"type": "boolean"},
                            "compliance_allowed": {"type": "boolean"},
                            "metric": {"type": "string"},
                            "currency": {"type": "string"},
                            "within_planning_horizon": {"type": "boolean"},
                            "horizon_ranking_eligible": {"type": "boolean"},
                            "expected_realization_date": {
                                "type": ["string", "null"]
                            },
                            "recommended_action": {"type": "string"},
                            "evidence": {"type": "object"},
                        },
                        "required": [
                            "candidate_id",
                            "expected_contribution",
                            "urgency",
                            "actionability",
                        ],
                    },
                },
                "constraints": {
                    "type": "object",
                    "properties": {
                        "top_k": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 50,
                            "description": (
                                "Maximum number of ranked recommendations to "
                                "return; defaults to 5 when omitted."
                            ),
                        },
                    },
                },
                "weights": {"type": "object"},
            },
            "required": ["agent_id", "objective", "candidates"],
        }

    async def execute(self, **kwargs: Any) -> str:
        return json.dumps(prioritize_followups(kwargs), ensure_ascii=False)
