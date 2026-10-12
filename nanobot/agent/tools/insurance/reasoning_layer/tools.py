"""Thin Tool adapters for deterministic insurance reasoning functions.

These adapters deliberately contain no insurance calculations.  They validate
the agent-supplied boundary values and delegate to the existing A2 functions.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.agent.tools.insurance.reasoning_layer.feasibility import (
    compute_feasibility,
)
from nanobot.agent.tools.insurance.reasoning_layer.run_rate import (
    compute_run_rate,
)


def _is_finite_number(value: object) -> bool:
    """Return whether value is a finite numeric value, excluding booleans."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


class CalculateRunRateTool(Tool):
    """Expose the existing run-rate calculation through the Tool contract."""

    @property
    def name(self) -> str:
        return "calculate_run_rate"

    @property
    def description(self) -> str:
        return (
            "Calculate performance run rate from supplied current and target values. "
            "This tool does not retrieve customer or performance data. When "
            "as_of_date is omitted, the calculation uses the current date."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "current": {
                    "type": "number",
                    "description": "Current performance value supplied for this calculation.",
                },
                "target": {
                    "type": "number",
                    "description": "Positive target performance value supplied for this calculation.",
                },
                "period_start": {
                    "type": ["string", "null"],
                    "description": "Optional ISO-8601 calendar date marking the period start.",
                },
                "as_of_date": {
                    "type": ["string", "null"],
                    "description": "Optional ISO-8601 calculation date; defaults to the current date.",
                },
            },
            "required": ["current", "target"],
        }

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        errors = super().validate_params(params)
        if errors:
            return errors

        for field in ("current", "target"):
            if not _is_finite_number(params[field]):
                errors.append(f"{field} must be finite")

        if (
            "target" in params
            and _is_finite_number(params["target"])
            and params["target"] <= 0
        ):
            errors.append("target must be greater than zero")

        for field in ("period_start", "as_of_date"):
            value = params.get(field)
            if value is None:
                continue
            try:
                date.fromisoformat(value)
            except ValueError:
                errors.append(f"{field} must be an ISO-8601 date")

        return errors

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        return compute_run_rate(
            current=kwargs["current"],
            target=kwargs["target"],
            period_start=kwargs.get("period_start"),
            as_of_date=kwargs.get("as_of_date"),
        )


class AssessGapFeasibilityTool(Tool):
    """Expose the existing gap-feasibility calculation through the Tool contract."""

    _UNIT_ALIASES = {
        "hkd": "HKD",
        "policies": "policies",
    }

    @property
    def name(self) -> str:
        return "assess_gap_feasibility"

    @property
    def description(self) -> str:
        return (
            "Assess gap-closing feasibility from supplied gap, time, and average values. "
            "This tool performs no database or customer-data lookup."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "actual_gap": {
                    "type": "number",
                    "description": "Remaining gap supplied for this calculation.",
                },
                "days_remaining": {
                    "type": "integer",
                    "description": "Days remaining; zero and negative values retain the A2 behavior.",
                },
                "monthly_avg": {
                    "type": "number",
                    "description": "Supplied recent monthly average used as the baseline.",
                },
                "unit": {
                    "type": "string",
                    "enum": ["HKD", "policies"],
                    "default": "HKD",
                    "description": (
                        "Supported calculation unit: HKD for currency gaps or policies "
                        "for policy-count gaps. Casing and surrounding whitespace are "
                        "normalized. Defaults to HKD when omitted."
                    ),
                },
            },
            "required": ["actual_gap", "days_remaining", "monthly_avg"],
        }

    @classmethod
    def _canonical_unit(cls, value: object) -> str | None:
        """Return a supported canonical unit without broadening A2 semantics."""
        if not isinstance(value, str):
            return None
        return cls._UNIT_ALIASES.get(value.strip().casefold())

    def cast_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Normalize documented unit spellings before schema validation."""
        cast_params = super().cast_params(params)
        if not isinstance(cast_params, dict) or "unit" not in cast_params:
            return cast_params

        canonical_unit = self._canonical_unit(cast_params["unit"])
        if canonical_unit is not None:
            cast_params["unit"] = canonical_unit
        return cast_params

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        errors = super().validate_params(params)
        if errors:
            return errors

        for field in ("actual_gap", "monthly_avg"):
            if not _is_finite_number(params[field]):
                errors.append(f"{field} must be finite")
        return errors

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        unit = self._canonical_unit(kwargs.get("unit", "HKD"))
        if unit is None:
            raise ValueError("unit must be a supported feasibility unit")

        return compute_feasibility(
            actual_gap=kwargs["actual_gap"],
            days_remaining=kwargs["days_remaining"],
            monthly_avg=kwargs["monthly_avg"],
            unit=unit,
        )
