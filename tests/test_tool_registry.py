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


if __name__ == "__main__":
    unittest.main()
