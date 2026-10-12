"""Deterministic tool-calling integration tests for AgentLoop."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from typing import Any

from nanobot.agent.loop import AgentLoop
from nanobot.agent.tools.base import Tool
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest


class ScriptedProvider(LLMProvider):
    """Provider double that records requests and never performs network I/O."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        super().__init__()
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {
                "messages": copy.deepcopy(messages),
                "tools": copy.deepcopy(tools),
                "model": model,
            }
        )
        return self.responses.pop(0)

    def get_default_model(self) -> str:
        return "fake-model"


class AddTool(Tool):
    @property
    def name(self) -> str:
        return "add"

    @property
    def description(self) -> str:
        return "Add two integers."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "left": {"type": "integer"},
                "right": {"type": "integer"},
            },
            "required": ["left", "right"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        return kwargs["left"] + kwargs["right"]


class AgentToolCallingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)

    async def asyncTearDown(self) -> None:
        self.temp_dir.cleanup()

    def _loop(
        self,
        responses: list[LLMResponse],
        *,
        registry: ToolRegistry | None = None,
        max_tool_iterations: int = 4,
    ) -> tuple[AgentLoop, ScriptedProvider]:
        provider = ScriptedProvider(responses)
        return (
            AgentLoop(
                bus=MessageBus(),
                provider=provider,
                workspace=self.workspace,
                tool_registry=registry,
                max_tool_iterations=max_tool_iterations,
            ),
            provider,
        )

    async def test_no_tool_text_response_preserves_existing_behavior(self) -> None:
        loop, provider = self._loop([LLMResponse(content="Plain answer")])

        result = await loop.process_direct("Hello")

        self.assertEqual(result.content, "Plain answer")
        self.assertEqual(provider.calls[0]["tools"], None)

    async def test_one_tool_call_is_followed_by_final_response(self) -> None:
        registry = ToolRegistry()
        registry.register(AddTool())
        loop, provider = self._loop(
            [
                LLMResponse(
                    content=None,
                    tool_calls=[
                        ToolCallRequest(
                            id="call-exact-id",
                            name="add",
                            arguments={"left": "2", "right": 3},
                        )
                    ],
                    finish_reason="tool_calls",
                ),
                LLMResponse(content="The sum is 5."),
            ],
            registry=registry,
        )

        result = await loop.process_direct("Add 2 and 3")

        self.assertEqual(result.content, "The sum is 5.")
        self.assertEqual(len(provider.calls), 2)
        self.assertEqual(provider.calls[0]["tools"], registry.get_definitions())
        assistant, tool_result = provider.calls[1]["messages"][-2:]
        self.assertEqual(assistant["role"], "assistant")
        self.assertEqual(assistant["tool_calls"][0]["id"], "call-exact-id")
        self.assertEqual(tool_result, {
            "role": "tool",
            "tool_call_id": "call-exact-id",
            "name": "add",
            "content": "5",
        })

    async def test_multiple_tool_calls_keep_order_and_pairing(self) -> None:
        registry = ToolRegistry()
        registry.register(AddTool())
        loop, provider = self._loop(
            [
                LLMResponse(
                    content=None,
                    tool_calls=[
                        ToolCallRequest("first", "add", {"left": 1, "right": 2}),
                        ToolCallRequest("second", "add", {"left": 3, "right": 4}),
                    ],
                ),
                LLMResponse(content="Both sums are ready."),
            ],
            registry=registry,
        )

        await loop.process_direct("Calculate both")

        history = provider.calls[1]["messages"]
        self.assertEqual(history[-3]["role"], "assistant")
        self.assertEqual(
            [(message["tool_call_id"], message["content"]) for message in history[-2:]],
            [("first", "3"), ("second", "7")],
        )

    async def test_iteration_limit_does_not_execute_unbounded_tool_calls(self) -> None:
        registry = ToolRegistry()
        registry.register(AddTool())
        loop, provider = self._loop(
            [
                LLMResponse(None, [ToolCallRequest("one", "add", {"left": 1, "right": 1})]),
                LLMResponse(None, [ToolCallRequest("two", "add", {"left": 2, "right": 2})]),
                LLMResponse(None, [ToolCallRequest("three", "add", {"left": 3, "right": 3})]),
            ],
            registry=registry,
            max_tool_iterations=2,
        )

        result = await loop.process_direct("Keep calculating")

        self.assertEqual(
            result.content,
            "Sorry, I couldn't complete the requested tool operations.",
        )
        self.assertEqual(len(provider.calls), 3)
        history = provider.calls[-1]["messages"]
        self.assertEqual(
            [message["tool_call_id"] for message in history if message["role"] == "tool"],
            ["one", "two"],
        )


if __name__ == "__main__":
    unittest.main()
