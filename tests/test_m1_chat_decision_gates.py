"""Scripted M1 feasibility decisions; no database or paid provider."""

from __future__ import annotations

import json
import unittest
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from nanobot.agent.loop import AgentLoop
from nanobot.agent.tools.insurance.reasoning_layer.composition import build_reasoning_registry
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMResponse


class FeasibilityDecisionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.registry = build_reasoning_registry(Path.cwd())
        self.provider = SimpleNamespace(
            get_default_model=lambda: "scripted-model",
            chat_with_retry=AsyncMock(return_value=LLMResponse(
                content="You can definitely achieve it; 99% certain.",
            )),
        )
        self.loop = AgentLoop(MessageBus(), self.provider, Path.cwd(),
                              tool_registry=self.registry)
        self.competition = {
            "id": "COMP_WRITTEN_PREMIUM_2026",
            "name": "2026 Written Premium Excellence Challenge",
            "name_en": "2026 Written Premium Excellence Challenge",
            "target_metric": "protection_premium", "unit": "USD",
            "current_value": 154750, "target_value": 818000,
            "gap": 663250, "days_remaining": 69,
            "deadline": (date.today() + timedelta(days=69)).isoformat(),
        }
        self.competition_tool = self.registry.get("get_competition_status")
        self.snapshot_tool = self.registry.get("get_performance_snapshot")
        self.competition_tool.execute = AsyncMock(side_effect=self.competition_result)
        self.snapshot_tool.execute = AsyncMock(side_effect=self.snapshot_result)

    async def competition_result(self, **kwargs):
        return json.dumps({"agent_id": kwargs["agent_id"], "competitions": [self.competition]})

    async def snapshot_result(self, **kwargs):
        return json.dumps({
            "agent_id": kwargs["agent_id"],
            "period": f"{date.today().year}-01-01 to {date.today().isoformat()}",
            "metrics": {"protection_premium": {
                "unit": "USD", "current": self.competition["current_value"],
            }},
        })

    async def ask(self, question="Can I still achieve my written premium target before the deadline?"):
        return await self.loop.process_direct(
            question, channel="websocket", chat_id="AGT00690",
            authenticated_agent_id="AGT00690",
        )

    async def test_low_result_overrides_positive_model_claim_without_model_tool_call(self):
        result = await self.ask()
        self.assertIn("very low feasibility (5%)", result.content)
        self.assertNotIn("99%", result.content)
        self.assertIn("nominal open gap", result.content)
        self.assertIn("pending premium", result.content)
        self.assertEqual(result.metadata["feasibility_decision"]["status"], "completed")
        self.assertEqual([event["name"] for event in result.metadata["tool_events"]], [
            "get_competition_status", "get_performance_snapshot",
            "calculate_run_rate", "assess_gap_feasibility",
        ])
        self.assertIsNone(self.provider.chat_with_retry.await_args.kwargs["tools"])
        self.assertEqual(self.provider.chat_with_retry.await_count, 1)

    async def test_high_result_overrides_negative_model_claim(self):
        self.competition.update(current_value=790000, gap=28000)
        self.provider.chat_with_retry.return_value = LLMResponse(content="Impossible.")
        result = await self.ask()
        self.assertIn("high feasibility", result.content)
        self.assertNotIn("Impossible", result.content)
        self.assertIn("does not guarantee the target will be reached", result.content)

    async def test_failed_or_malformed_deterministic_tool_is_neutral(self):
        tool = self.registry.get("assess_gap_feasibility")
        for response in (RuntimeError("offline"), {"level": "high"},
                         {"level": "high", "probability_pct": 95}, "not JSON"):
            with self.subTest(response=type(response).__name__):
                tool.execute = AsyncMock(side_effect=response if isinstance(response, Exception) else None,
                                         return_value=None if isinstance(response, Exception) else response)
                result = await self.ask()
                self.assertIn("assessment unavailable", result.content.lower())
                self.assertNotIn("99%", result.content)
                self.assertNotIn("feasibility is high", result.content)
                self.assertEqual(result.metadata["feasibility_decision"]["status"], "unavailable")

    async def test_wrong_agent_target_currency_or_missing_input_fails_closed(self):
        self.competition_tool.execute = AsyncMock(return_value=json.dumps({
            "agent_id": "other-agent", "competitions": [self.competition],
        }))
        self.assertIn("assessment unavailable", (await self.ask()).content.lower())
        self.competition_tool.execute = AsyncMock(side_effect=self.competition_result)
        self.assertIn("one specific target", (await self.ask("Can I achieve my COT target?")).content)
        self.competition["unit"] = "HKD"
        self.assertIn("matching USD", (await self.ask()).content)
        self.competition["unit"] = "policies"
        self.assertIn("matching USD", (await self.ask()).content)
        self.competition["unit"] = "USD"
        self.assertIn("requested HKD target",
                      (await self.ask("Can I achieve my HKD written premium target?")).content)
        self.assertIn("policy-count target",
                      (await self.ask("Can I achieve my written premium policy-count target?")).content)
        self.snapshot_tool.execute = AsyncMock(return_value=json.dumps({
            "agent_id": "AGT00690", "metrics": {},
        }))
        self.assertIn("snapshot is missing", (await self.ask()).content)

    async def test_unrelated_chat_uses_normal_provider_response(self):
        result = await self.ask("Hello")
        self.assertEqual(result.content, "You can definitely achieve it; 99% certain.")
        self.assertNotIn("feasibility_decision", result.metadata)
        self.competition_tool.execute.assert_not_awaited()

    async def test_unauthenticated_direct_call_cannot_read_agent_feasibility_data(self):
        result = await self.loop.process_direct(
            "Can I still achieve my written premium target?",
            channel="websocket", chat_id="AGT00690",
        )
        self.assertNotIn("feasibility_decision", result.metadata)
        self.competition_tool.execute.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
