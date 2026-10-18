"""Offline retry and cancellation contracts for the shared provider base."""

from __future__ import annotations

import asyncio
import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from nanobot.providers.base import GenerationSettings, LLMProvider, LLMResponse


class ScriptedProvider(LLMProvider):
    def __init__(self, outcomes: list[LLMResponse | BaseException]) -> None:
        super().__init__()
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    async def chat(self, **kwargs: Any) -> LLMResponse:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def get_default_model(self) -> str:
        return "offline-scripted-model"


class ProviderRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_errors_retry_with_exponential_waits(self) -> None:
        provider = ScriptedProvider([
            LLMResponse(content="429 rate limit", finish_reason="error"),
            LLMResponse(content="timeout", finish_reason="error"),
            LLMResponse(content="503 unavailable", finish_reason="error"),
            LLMResponse(content="Recovered"),
        ])

        with patch("nanobot.providers.base.asyncio.sleep", new_callable=AsyncMock) as sleep:
            response = await provider.chat_with_retry(messages=[{"role": "user", "content": "Hi"}])

        self.assertEqual(response.content, "Recovered")
        self.assertEqual(len(provider.calls), 4)
        self.assertEqual([call.args for call in sleep.await_args_list], [(1,), (2,), (4,)])

    async def test_non_transient_authentication_error_does_not_retry(self) -> None:
        provider = ScriptedProvider([
            LLMResponse(content="401 unauthorized", finish_reason="error")
        ])

        with patch("nanobot.providers.base.asyncio.sleep", new_callable=AsyncMock) as sleep:
            response = await provider.chat_with_retry(messages=[])

        self.assertEqual(response.finish_reason, "error")
        self.assertEqual(len(provider.calls), 1)
        sleep.assert_not_awaited()

    async def test_cancellation_propagates_without_retry(self) -> None:
        provider = ScriptedProvider([asyncio.CancelledError()])

        with patch("nanobot.providers.base.asyncio.sleep", new_callable=AsyncMock) as sleep:
            with self.assertRaises(asyncio.CancelledError):
                await provider.chat_with_retry(messages=[])

        self.assertEqual(len(provider.calls), 1)
        sleep.assert_not_awaited()

    async def test_generation_defaults_and_explicit_overrides_reach_chat(self) -> None:
        provider = ScriptedProvider([LLMResponse("one"), LLMResponse("two")])
        provider.generation = GenerationSettings(
            temperature=0.2, max_tokens=128, reasoning_effort="low"
        )

        await provider.chat_with_retry(messages=[], model="offline-model")
        await provider.chat_with_retry(
            messages=[], model="offline-model", temperature=0.6,
            max_tokens=256, reasoning_effort=None,
        )

        first, second = provider.calls
        self.assertEqual(
            (first["temperature"], first["max_tokens"], first["reasoning_effort"]),
            (0.2, 128, "low"),
        )
        self.assertEqual(
            (second["temperature"], second["max_tokens"], second["reasoning_effort"]),
            (0.6, 256, None),
        )
        self.assertEqual(first["model"], "offline-model")


if __name__ == "__main__":
    unittest.main()
