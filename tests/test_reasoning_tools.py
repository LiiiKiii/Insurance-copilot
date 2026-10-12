"""Offline tests for the deterministic insurance reasoning Tool adapters."""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from api.state import RuntimeState
from nanobot.agent.tools.insurance.reasoning_layer.composition import (
    build_reasoning_registry,
)
from nanobot.agent.tools.insurance.reasoning_layer.feasibility import (
    compute_feasibility,
)
from nanobot.agent.tools.insurance.reasoning_layer.run_rate import compute_run_rate
from nanobot.agent.tools.insurance.reasoning_layer.tools import (
    AssessGapFeasibilityTool,
    CalculateRunRateTool,
)
from nanobot.config.schema import Config
from nanobot.providers.base import LLMProvider, LLMResponse


class NoNetworkProvider(LLMProvider):
    """Provider double used to prove RuntimeState setup makes no request."""

    async def chat(self, *args: object, **kwargs: object) -> LLMResponse:
        raise AssertionError("RuntimeState construction must not call a provider")

    def get_default_model(self) -> str:
        return "fake-model"


class ReasoningToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_state_injects_a_fresh_explicit_reasoning_registry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Config.model_validate(
                {
                    "agents": {
                        "defaults": {
                            "workspace": str(Path(directory)),
                            "model": "fake-model",
                            "provider": "openrouter",
                        }
                    },
                    "providers": {"openrouter": {"apiKey": "test-key"}},
                }
            )
            runtime = RuntimeState(config=config, provider=NoNetworkProvider())

        self.assertIs(runtime.agent_loop.tool_registry, runtime.tool_registry)
        self.assertEqual(
            runtime.tool_registry.tool_names,
            ("calculate_run_rate", "assess_gap_feasibility"),
        )

    async def test_composition_registers_only_the_two_explicit_reasoning_tools(self) -> None:
        registry = build_reasoning_registry()

        self.assertEqual(
            registry.tool_names,
            ("calculate_run_rate", "assess_gap_feasibility"),
        )
        self.assertEqual(
            [definition["function"]["name"] for definition in registry.get_definitions()],
            ["calculate_run_rate", "assess_gap_feasibility"],
        )

    async def test_run_rate_schema_has_only_calculation_inputs(self) -> None:
        tool = CalculateRunRateTool()
        schema = tool.to_schema()["function"]

        self.assertEqual(schema["name"], "calculate_run_rate")
        self.assertEqual(schema["parameters"]["required"], ["current", "target"])
        self.assertEqual(
            set(schema["parameters"]["properties"]),
            {"current", "target", "period_start", "as_of_date"},
        )
        self.assertIn("does not retrieve", schema["description"])
        self.assertIn("current date", schema["description"])

    async def test_run_rate_delegates_exactly_to_a2_function(self) -> None:
        tool = CalculateRunRateTool()
        inputs = {
            "current": 120_000.0,
            "target": 240_000.0,
            "period_start": "2026-01-01",
            "as_of_date": "2026-04-01",
        }

        self.assertEqual(
            await tool.execute(**inputs),
            compute_run_rate(**inputs),
        )

    async def test_run_rate_registry_casts_numbers_and_serializes_a2_result(self) -> None:
        registry = build_reasoning_registry()
        result = await registry.execute(
            "calculate_run_rate",
            {
                "current": "120000",
                "target": "240000",
                "period_start": "2026-01-01",
                "as_of_date": "2026-04-01",
            },
        )

        self.assertEqual(
            json.loads(result),
            compute_run_rate(120000.0, 240000.0, "2026-01-01", "2026-04-01"),
        )

    async def test_run_rate_rejects_missing_invalid_and_non_finite_inputs(self) -> None:
        registry = build_reasoning_registry()
        invalid_inputs = (
            {"current": 100},
            {"current": 100, "target": 0},
            {"current": 100, "target": -1},
            {"current": math.nan, "target": 100},
            {"current": 100, "target": math.inf},
            {"current": 100, "target": 200, "as_of_date": "04-01-2026"},
            {"current": 100, "target": 200, "period_start": "2026-02-30"},
        )

        for params in invalid_inputs:
            with self.subTest(params=params):
                self.assertEqual(
                    await registry.execute("calculate_run_rate", params),
                    "Tool arguments are invalid.",
                )

    async def test_feasibility_schema_has_supported_units_and_no_record_identifiers(self) -> None:
        tool = AssessGapFeasibilityTool()
        schema = tool.to_schema()["function"]

        self.assertEqual(schema["name"], "assess_gap_feasibility")
        self.assertEqual(
            schema["parameters"]["required"],
            ["actual_gap", "days_remaining", "monthly_avg"],
        )
        self.assertEqual(schema["parameters"]["properties"]["unit"]["default"], "HKD")
        self.assertEqual(
            schema["parameters"]["properties"]["unit"]["enum"],
            ["HKD", "policies"],
        )
        self.assertEqual(
            set(schema["parameters"]["properties"]),
            {"actual_gap", "days_remaining", "monthly_avg", "unit"},
        )
        self.assertIn("no database", schema["description"])

    async def test_feasibility_delegates_to_a2_for_hkd_policies_and_nonpositive_days(self) -> None:
        tool = AssessGapFeasibilityTool()
        cases = (
            {"actual_gap": 24_000.0, "days_remaining": 30, "monthly_avg": 30_000.0},
            {
                "actual_gap": 24_000.0,
                "days_remaining": 30,
                "monthly_avg": 30_000.0,
                "unit": "policies",
            },
            {"actual_gap": 24_000.0, "days_remaining": 0, "monthly_avg": 30_000.0},
            {"actual_gap": 24_000.0, "days_remaining": -5, "monthly_avg": 30_000.0},
        )

        for inputs in cases:
            with self.subTest(inputs=inputs):
                self.assertEqual(
                    await tool.execute(**inputs),
                    compute_feasibility(**inputs),
                )

    async def test_feasibility_normalizes_supported_units_and_preserves_default_hkd(self) -> None:
        registry = build_reasoning_registry()
        inputs = {"actual_gap": "24000", "days_remaining": "30", "monthly_avg": "30000"}
        unit_cases = (
            (None, "HKD"),
            ("HKD", "HKD"),
            ("hkd", "HKD"),
            (" HKD ", "HKD"),
            ("policies", "policies"),
            ("POLICIES", "policies"),
            (" Policies ", "policies"),
        )

        for supplied_unit, canonical_unit in unit_cases:
            with self.subTest(supplied_unit=supplied_unit):
                params = dict(inputs)
                if supplied_unit is not None:
                    params["unit"] = supplied_unit
                result = await registry.execute("assess_gap_feasibility", params)
                self.assertEqual(
                    json.loads(result),
                    compute_feasibility(24000.0, 30, 30000.0, canonical_unit),
                )

    async def test_feasibility_rejects_missing_nonfinite_and_noninteger_inputs(self) -> None:
        registry = build_reasoning_registry()
        invalid_inputs = (
            {"actual_gap": 1, "days_remaining": 1},
            {"actual_gap": math.inf, "days_remaining": 1, "monthly_avg": 1},
            {"actual_gap": 1, "days_remaining": 1, "monthly_avg": math.nan},
            {"actual_gap": 1, "days_remaining": "1.5", "monthly_avg": 1},
            {"actual_gap": 1, "days_remaining": 1, "monthly_avg": 1, "unit": ""},
            {"actual_gap": 1, "days_remaining": 1, "monthly_avg": 1, "unit": "policy"},
            {"actual_gap": 1, "days_remaining": 1, "monthly_avg": 1, "unit": "typo"},
            {"actual_gap": 1, "days_remaining": 1, "monthly_avg": 1, "unit": "cases"},
        )

        for params in invalid_inputs:
            with self.subTest(params=params):
                self.assertEqual(
                    await registry.execute("assess_gap_feasibility", params),
                    "Tool arguments are invalid.",
                )


if __name__ == "__main__":
    unittest.main()
