"""Offline contract and WebSocket integration tests for compliance post-processing."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from api import compliance
from api.compliance import apply_compliance
from api.server import create_app


class WebSocketHarness:
    """Small in-process ASGI harness for the real WebSocket endpoint."""

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
        accepted = await self.outgoing.get()
        if accepted["type"] != "websocket.accept":
            raise AssertionError(f"Expected accept, received {accepted!r}")

    async def send_json(self, payload: object) -> dict[str, Any]:
        await self.incoming.put(
            {"type": "websocket.receive", "text": json.dumps(payload)}
        )
        event = await self.outgoing.get()
        if event["type"] != "websocket.send":
            raise AssertionError(f"Expected send, received {event!r}")
        return json.loads(event["text"])

    async def disconnect(self) -> None:
        await self.incoming.put({"type": "websocket.disconnect", "code": 1000})
        if self.task is not None:
            await self.task


class ComplianceTests(unittest.IsolatedAsyncioTestCase):
    def test_no_match_leaves_text_unchanged(self) -> None:
        text = "Please confirm the current policy wording with your manager."

        self.assertEqual(apply_compliance(text), (text, False, []))

    def test_case_insensitive_match_appends_disclaimer_once(self) -> None:
        text = "This benefit is GUARANTEED."
        processed, matched, keywords = apply_compliance(text)

        self.assertTrue(matched)
        self.assertIn("guarantee", keywords)
        self.assertTrue(processed.startswith(text))
        self.assertEqual(processed.count(compliance._load_policy()[1]), 1)

    def test_multiple_matches_follow_configured_keyword_order(self) -> None:
        text = "There is zero risk because the insurer must pay."

        _, matched, keywords = apply_compliance(text)

        self.assertTrue(matched)
        self.assertEqual(keywords, ["must pay", "zero risk"])

    def test_existing_disclaimer_is_not_duplicated(self) -> None:
        disclaimer = compliance._load_policy()[1]
        text = f"We guarantee approval.\n\n{disclaimer}"

        processed, matched, _ = apply_compliance(text)

        self.assertTrue(matched)
        self.assertEqual(processed, text)
        self.assertEqual(processed.count(disclaimer), 1)

    def test_empty_text_is_unchanged(self) -> None:
        self.assertEqual(apply_compliance(""), ("", False, []))

    def test_invalid_or_missing_policy_uses_documented_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing_path = Path(directory) / "missing.json"
            with patch.object(compliance, "_POLICY_PATH", missing_path):
                processed, matched, keywords = apply_compliance("A guarantee is offered.")

        self.assertTrue(matched)
        self.assertEqual(keywords, ["guarantee"])
        self.assertEqual(processed, "A guarantee is offered.\n\n" + compliance._DEFAULT_DISCLAIMER)

    async def test_websocket_success_response_is_processed(self) -> None:
        class FakeAgentLoop:
            async def process_direct(self, **kwargs: str) -> object:
                return SimpleNamespace(content="This outcome is guaranteed.")

        runtime = SimpleNamespace(is_running=True, agent_loop=FakeAgentLoop())
        socket = WebSocketHarness(create_app(runtime=runtime))
        await socket.connect()
        try:
            event = await socket.send_json(
                {"message": "Explain", "agent_id": "AGT001", "turn_id": "turn:1"}
            )
        finally:
            await socket.disconnect()

        disclaimer = compliance._load_policy()[1]
        self.assertEqual(event["type"], "response")
        self.assertEqual(event["turn_id"], "turn:1")
        self.assertTrue(event["content"].startswith("This outcome is guaranteed."))
        self.assertEqual(event["content"].count(disclaimer), 1)

    async def test_websocket_error_response_is_unchanged(self) -> None:
        runtime = SimpleNamespace(is_running=False, agent_loop=None)
        socket = WebSocketHarness(create_app(runtime=runtime))
        await socket.connect()
        try:
            event = await socket.send_json(
                {"message": "Explain", "agent_id": "AGT001", "turn_id": "turn:2"}
            )
        finally:
            await socket.disconnect()

        self.assertEqual(
            event,
            {
                "type": "error",
                "content": "Agent runtime is unavailable.",
                "turn_id": "turn:2",
            },
        )


if __name__ == "__main__":
    unittest.main()
