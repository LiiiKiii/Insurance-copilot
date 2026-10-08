"""Offline end-to-end coverage for insurance reasoning tool calls."""

from __future__ import annotations

import asyncio
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from api.server import create_app
from nanobot.agent.loop import AgentLoop
from nanobot.agent.tools.insurance.reasoning_layer.composition import (
    build_reasoning_registry,
)
from nanobot.agent.tools.insurance.reasoning_layer.run_rate import compute_run_rate
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest


class ScriptedProvider(LLMProvider):
    """A provider double that records inputs and cannot make network calls."""

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
            {"messages": copy.deepcopy(messages), "tools": copy.deepcopy(tools), "model": model}
        )
        return self.responses.pop(0)

    def get_default_model(self) -> str:
        return "fake-model"


class WebSocketHarness:
    """Small in-process ASGI WebSocket harness used with the real route."""

    def __init__(self, application: Any) -> None:
        self.application = application
        self.incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.outgoing: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        async def receive() -> dict[str, Any]:
            return await self.incoming.get()

        async def send(message: dict[str, Any]) -> None:
            await self.outgoing.put(message)

        self.task = asyncio.create_task(
            self.application(
                {
                    "type": "websocket",
                    "asgi": {"version": "3.0"},
                    "scheme": "ws",
                    "path": "/ws/chat",
                    "raw_path": b"/ws/chat",
                    "query_string": b"",
                    "headers": [],
                    "client": ("127.0.0.1", 12345),
                    "server": ("testserver", 80),
                    "subprotocols": [],
                },
                receive,
                send,
            )
        )
        await self.incoming.put({"type": "websocket.connect"})
        self.assertEqual((await self.outgoing.get())["type"], "websocket.accept")

    async def request(self, payload: dict[str, str]) -> dict[str, str]:
        await self.incoming.put({"type": "websocket.receive", "text": json.dumps(payload)})
        event = await self.outgoing.get()
        self.assertEqual(event["type"], "websocket.send")
        return json.loads(event["text"])

    async def close(self) -> None:
        await self.incoming.put({"type": "websocket.disconnect", "code": 1000})
        if self.task is not None:
            await self.task

    def assertEqual(self, first: Any, second: Any) -> None:
        if first != second:
            raise AssertionError(f"{first!r} != {second!r}")


class ReasoningToolCallingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)

    async def asyncTearDown(self) -> None:
        self.temp_dir.cleanup()

    def _loop(self, provider: ScriptedProvider) -> AgentLoop:
        return AgentLoop(
            bus=MessageBus(),
            provider=provider,
            workspace=self.workspace,
            tool_registry=build_reasoning_registry(),
        )

    def _tool_then_answer_provider(self) -> ScriptedProvider:
        return ScriptedProvider(
            [
                LLMResponse(
                    content=None,
                    tool_calls=[
                        ToolCallRequest(
                            id="run-rate-call",
                            name="calculate_run_rate",
                            arguments={
                                "current": "120000",
                                "target": "240000",
                                "period_start": "2026-01-01",
                                "as_of_date": "2026-04-01",
                            },
                        )
                    ],
                    finish_reason="tool_calls",
                ),
                LLMResponse(content="The supplied performance is behind pace."),
            ]
        )

    async def test_real_loop_preserves_assistant_tool_history_pairing(self) -> None:
        provider = self._tool_then_answer_provider()
        loop = self._loop(provider)

        response = await loop.process_direct("Assess my supplied performance")

        self.assertEqual(response.content, "The supplied performance is behind pace.")
        self.assertEqual(len(provider.calls), 2)
        self.assertEqual(
            [item["function"]["name"] for item in provider.calls[0]["tools"]],
            ["calculate_run_rate", "assess_gap_feasibility"],
        )
        assistant, tool_result = provider.calls[1]["messages"][-2:]
        self.assertEqual(assistant["role"], "assistant")
        self.assertEqual(assistant["tool_calls"][0]["id"], "run-rate-call")
        self.assertEqual(tool_result["role"], "tool")
        self.assertEqual(tool_result["tool_call_id"], "run-rate-call")
        self.assertEqual(tool_result["name"], "calculate_run_rate")
        self.assertEqual(
            json.loads(tool_result["content"]),
            compute_run_rate(120000.0, 240000.0, "2026-01-01", "2026-04-01"),
        )

    async def test_existing_websocket_route_returns_answer_from_real_loop(self) -> None:
        provider = self._tool_then_answer_provider()
        runtime = SimpleNamespace(is_running=True, agent_loop=self._loop(provider))
        socket = WebSocketHarness(create_app(runtime=runtime))
        await socket.connect()
        try:
            event = await socket.request(
                {"message": "Assess my supplied performance", "agent_id": "AGT001"}
            )
        finally:
            await socket.close()

        self.assertEqual(event["type"], "response")
        self.assertEqual(event["content"], "The supplied performance is behind pace.")
        self.assertEqual(len(provider.calls), 2)


if __name__ == "__main__":
    unittest.main()
