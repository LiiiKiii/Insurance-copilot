"""Focused lifecycle tests for the A3 application runtime state."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from api.state import RuntimeState
from nanobot.config.schema import Config
from nanobot.providers.base import LLMProvider, LLMResponse
from nanobot.providers.openai_compat_provider import OpenAICompatProvider


class FakeProvider(LLMProvider):
    """Provider double that never performs network I/O."""

    def __init__(self, default_model: str = "fake-model") -> None:
        super().__init__()
        self.default_model = default_model
        self.calls: list[dict] = []

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {
                "messages": messages,
                "tools": tools,
                "model": model,
            }
        )
        return LLMResponse(content="unused")

    def get_default_model(self) -> str:
        return self.default_model


def make_config(workspace: Path) -> Config:
    """Build test configuration without reading environment credentials."""
    return Config.model_validate(
        {
            "agents": {
                "defaults": {
                    "workspace": str(workspace),
                    "model": "configured-model",
                    "provider": "openrouter",
                }
            },
            "providers": {"openrouter": {"apiKey": "test-key"}},
        }
    )


class RuntimeStateTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.config = make_config(self.workspace)
        self.provider = FakeProvider()
        self.runtime = RuntimeState(
            config=self.config,
            provider=self.provider,
        )

    async def asyncTearDown(self) -> None:
        await self.runtime.stop()
        self.temp_dir.cleanup()

    async def test_construction_is_side_effect_free(self) -> None:
        self.assertIs(self.runtime.config, self.config)
        self.assertIs(self.runtime.provider, self.provider)
        self.assertEqual(self.runtime.workspace, self.workspace)
        self.assertFalse(self.runtime.is_running)
        self.assertIsNone(self.runtime.agent_task)
        self.assertEqual(self.provider.calls, [])

    async def test_configured_provider_is_resolved_without_a_request(self) -> None:
        runtime = RuntimeState(config=self.config)

        self.assertIsInstance(runtime.provider, OpenAICompatProvider)
        self.assertEqual(runtime.provider.get_default_model(), "configured-model")
        self.assertFalse(runtime.is_running)

    async def test_injected_provider_is_used_by_agent_loop(self) -> None:
        self.assertIs(self.runtime.agent_loop.provider, self.provider)
        self.assertIs(self.runtime.agent_loop.bus, self.runtime.bus)

    async def test_agent_loop_uses_configured_workspace_and_model(self) -> None:
        self.assertEqual(self.runtime.agent_loop.workspace, self.workspace)
        self.assertEqual(self.runtime.agent_loop.model, "configured-model")

    async def test_start_creates_a_background_task(self) -> None:
        await self.runtime.start()

        self.assertTrue(self.runtime.is_running)
        self.assertIsNotNone(self.runtime.agent_task)
        self.assertEqual(self.provider.calls, [])

    async def test_repeated_start_reuses_existing_task(self) -> None:
        await self.runtime.start()
        first_task = self.runtime.agent_task

        await self.runtime.start()

        self.assertIs(self.runtime.agent_task, first_task)
        self.assertTrue(self.runtime.is_running)

    async def test_stop_cancels_and_clears_background_task(self) -> None:
        await self.runtime.start()
        task = self.runtime.agent_task

        await self.runtime.stop()

        self.assertIsNotNone(task)
        self.assertTrue(task.done())
        self.assertIsNone(self.runtime.agent_task)
        self.assertFalse(self.runtime.is_running)

    async def test_repeated_stop_is_safe(self) -> None:
        await self.runtime.start()
        await self.runtime.stop()
        await self.runtime.stop()

        self.assertIsNone(self.runtime.agent_task)
        self.assertFalse(self.runtime.is_running)

    async def test_start_after_stop_creates_a_new_task(self) -> None:
        await self.runtime.start()
        first_task = self.runtime.agent_task

        await self.runtime.stop()
        await self.runtime.start()

        self.assertIsNotNone(first_task)
        self.assertIsNot(self.runtime.agent_task, first_task)
        self.assertTrue(self.runtime.is_running)

    async def test_cancelled_agent_task_is_cleaned_up_by_stop(self) -> None:
        await self.runtime.start()
        task = self.runtime.agent_task
        self.assertIsNotNone(task)

        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await self.runtime.stop()

        self.assertIsNone(self.runtime.agent_task)
        self.assertFalse(self.runtime.is_running)

    async def test_start_propagates_failure_and_clears_completed_task(self) -> None:
        async def fail_run() -> None:
            raise RuntimeError("simulated loop failure")

        self.runtime.agent_loop.run = fail_run  # type: ignore[method-assign]
        await self.runtime.start()
        await asyncio.sleep(0)

        with self.assertRaisesRegex(RuntimeError, "AgentLoop stopped unexpectedly"):
            await self.runtime.start()

        self.assertIsNone(self.runtime.agent_task)
        self.assertFalse(self.runtime.is_running)

    async def test_stop_cleans_up_after_an_agent_task_failure(self) -> None:
        async def fail_run() -> None:
            raise RuntimeError("simulated loop failure")

        self.runtime.agent_loop.run = fail_run  # type: ignore[method-assign]
        await self.runtime.start()
        await asyncio.sleep(0)

        await self.runtime.stop()

        self.assertIsNone(self.runtime.agent_task)
        self.assertFalse(self.runtime.is_running)


if __name__ == "__main__":
    unittest.main()
