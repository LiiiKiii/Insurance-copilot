"""Unit tests for safe generic ToolRegistry execution."""

from __future__ import annotations

import asyncio
import unittest
from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.agent.tools.registry import ToolRegistry


class ExampleTool(Tool):
    @property
    def name(self) -> str:
        return "example"

    @property
    def description(self) -> str:
        return "Return a validated value."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
            "required": ["count"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        return {"count": kwargs["count"]}


class FailingTool(ExampleTool):
    @property
    def name(self) -> str:
        return "failing"

    async def execute(self, **kwargs: Any) -> Any:
        raise RuntimeError("credential=secret-value")


class SlowTool(ExampleTool):
    @property
    def name(self) -> str:
        return "slow"

    async def execute(self, **kwargs: Any) -> Any:
        await asyncio.sleep(1)
        return "late"


class OversizedTool(ExampleTool):
    @property
    def name(self) -> str:
        return "oversized"

    async def execute(self, **kwargs: Any) -> Any:
        return {"private_value": "x" * 100}


class NestedSchemaTool(Tool):
    def __init__(self) -> None:
        self.received: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "nested"

    @property
    def description(self) -> str:
        return "Validate nested business inputs."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["quote", "renew"]},
                "enabled": {"type": "boolean"},
                "ratio": {"type": "number", "minimum": 0, "maximum": 1},
                "note": {"type": ["string", "null"], "minLength": 3},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"amount": {"type": "integer", "minimum": 1}},
                        "required": ["amount"],
                    },
                },
            },
            "required": ["mode", "items"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        self.received.append(kwargs)
        return {"accepted": len(kwargs["items"])}


class ToolRegistryTests(unittest.IsolatedAsyncioTestCase):
    async def test_register_retrieve_unregister_and_reject_duplicates(self) -> None:
        registry = ToolRegistry()
        tool = ExampleTool()

        registry.register(tool)

        self.assertIs(registry.get("example"), tool)
        self.assertTrue(registry.has("example"))
        self.assertEqual(registry.tool_names, ("example",))
        with self.assertRaisesRegex(ValueError, "already registered"):
            registry.register(tool)
        self.assertIs(registry.unregister("example"), tool)
        self.assertFalse(registry.has("example"))

    async def test_definitions_use_openai_function_schema(self) -> None:
        registry = ToolRegistry()
        registry.register(ExampleTool())

        self.assertEqual(
            registry.get_definitions(),
            [
                {
                    "type": "function",
                    "function": {
                        "name": "example",
                        "description": "Return a validated value.",
                        "parameters": ExampleTool().parameters,
                    },
                }
            ],
        )

    async def test_execute_casts_valid_arguments(self) -> None:
        registry = ToolRegistry()
        registry.register(ExampleTool())

        result = await registry.execute("example", {"count": "3"})

        self.assertEqual(result, '{"count": 3}')

    async def test_invalid_and_unknown_arguments_are_sanitized(self) -> None:
        registry = ToolRegistry()
        registry.register(ExampleTool())

        self.assertEqual(
            await registry.execute("example", {"count": "not-an-integer"}),
            "Tool arguments are invalid.",
        )
        self.assertEqual(
            await registry.execute("missing", {}),
            "Tool is not available.",
        )

    async def test_execution_exception_is_sanitized(self) -> None:
        registry = ToolRegistry()
        registry.register(FailingTool())

        result = await registry.execute("failing", {"count": 1})

        self.assertEqual(result, "Tool execution failed.")
        self.assertNotIn("secret-value", result)

    async def test_execution_timeout_is_sanitized(self) -> None:
        registry = ToolRegistry(timeout_seconds=0.01)
        registry.register(SlowTool())

        self.assertEqual(
            await registry.execute("slow", {"count": 1}),
            "Tool execution timed out.",
        )

    async def test_audit_status_matches_execution_boundary(self) -> None:
        registry = ToolRegistry(timeout_seconds=0.01)
        for tool in (ExampleTool(), FailingTool(), SlowTool()):
            registry.register(tool)

        for name, params, expected in (
            ("example", {"count": 1}, "completed"),
            ("example", {"count": "bad"}, "invalid_parameters"),
            ("missing", {}, "unknown_tool"),
            ("failing", {"count": 1}, "execution_failed"),
            ("slow", {"count": 1}, "timed_out"),
        ):
            with self.subTest(name=name, expected=expected):
                _content, status = await registry.execute_with_status(name, params)
                self.assertEqual(status, expected)

    async def test_oversized_result_is_not_truncated_into_invalid_json(self) -> None:
        registry = ToolRegistry(max_result_chars=50)
        registry.register(OversizedTool())

        content, status = await registry.execute_with_status("oversized", {"count": 1})

        self.assertEqual(status, "result_too_large")
        self.assertEqual(content, "Tool result exceeded size limit.")
        self.assertNotIn("private_value", content)

    async def test_nested_casting_and_unknown_fields_preserve_valid_input(self) -> None:
        tool = NestedSchemaTool()
        registry = ToolRegistry()
        registry.register(tool)

        result = await registry.execute(
            "nested",
            {
                "mode": "quote",
                "enabled": "yes",
                "ratio": "0.5",
                "note": None,
                "items": [{"amount": "2", "external_id": "record-1"}],
                "correlation_id": "request-1",
            },
        )

        self.assertEqual(result, '{"accepted": 1}')
        self.assertEqual(
            tool.received,
            [{
                "mode": "quote",
                "enabled": True,
                "ratio": 0.5,
                "note": None,
                "items": [{"amount": 2, "external_id": "record-1"}],
                "correlation_id": "request-1",
            }],
        )

    async def test_nested_schema_rejects_invalid_values_without_executing(self) -> None:
        tool = NestedSchemaTool()
        registry = ToolRegistry()
        registry.register(tool)
        cases = (
            ({"items": []}, "missing required mode"),
            ({"mode": "other", "items": []}, "mode must be one of"),
            ({"mode": "quote", "items": [{}]}, "missing required items[0].amount"),
            ({"mode": "quote", "items": [{"amount": 0}]}, "items[0].amount must be >= 1"),
            ({"mode": "quote", "items": [], "ratio": 1.1}, "ratio must be <= 1"),
            ({"mode": "quote", "items": [], "note": "ab"}, "note must be at least 3 chars"),
            ({"mode": "quote", "items": [], "enabled": "maybe"}, "enabled should be boolean"),
            ({"mode": "quote", "items": "one"}, "items should be array"),
            ({"mode": "quote", "items": [{"amount": True}]}, "items[0].amount should be integer"),
        )
        for params, expected_error in cases:
            with self.subTest(params=params):
                cast = tool.cast_params(params)
                self.assertTrue(
                    any(expected_error in error for error in tool.validate_params(cast))
                )
                self.assertEqual(
                    await registry.execute("nested", params),
                    "Tool arguments are invalid.",
                )
        self.assertEqual(tool.received, [])

    def test_boolean_never_validates_as_number_or_integer(self) -> None:
        class NumericTool(ExampleTool):
            @property
            def parameters(self) -> dict[str, Any]:
                return {
                    "type": "object",
                    "properties": {
                        "count": {"type": "integer"},
                        "ratio": {"type": "number"},
                    },
                    "required": ["count", "ratio"],
                }

        tool = NumericTool()
        self.assertEqual(
            tool.validate_params(tool.cast_params({"count": True, "ratio": False})),
            ["count should be integer", "ratio should be number"],
        )


if __name__ == "__main__":
    unittest.main()
