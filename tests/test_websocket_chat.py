"""Offline ASGI integration tests for the WebSocket chat endpoint."""

from __future__ import annotations

import asyncio
import json
import unittest
from types import SimpleNamespace

try:
    from api.server import create_app
    from api.ws import router as websocket_router
    from fastapi.routing import APIWebSocketRoute
except ModuleNotFoundError as exc:
    create_app = None
    websocket_router = None
    APIWebSocketRoute = None
    IMPORT_ERROR = str(exc)
else:
    IMPORT_ERROR = ""


@unittest.skipUnless(
    create_app is not None,
    f"FastAPI test dependencies are unavailable: {IMPORT_ERROR}",
)
class WebSocketChatTests(unittest.IsolatedAsyncioTestCase):
    class FakeAgentLoop:
        def __init__(self) -> None:
            self.calls: list[dict[str, str]] = []
            self.error: Exception | None = None
            self.result: object | None = SimpleNamespace(content="Fake agent answer")

        async def process_direct(self, **kwargs: str) -> object | None:
            self.calls.append(kwargs)
            if self.error is not None:
                raise self.error
            return self.result

    class FakeRuntime:
        def __init__(self, *, is_running: bool = True) -> None:
            self.is_running = is_running
            self.agent_loop = WebSocketChatTests.FakeAgentLoop()

    class WebSocketHarness:
        def __init__(self, application) -> None:
            self.application = application
            self.incoming: asyncio.Queue[dict] = asyncio.Queue()
            self.outgoing: asyncio.Queue[dict] = asyncio.Queue()
            self.task: asyncio.Task[None] | None = None

        async def connect(self) -> None:
            async def receive() -> dict:
                return await self.incoming.get()

            async def send(message: dict) -> None:
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

        async def send_json(self, payload: object) -> None:
            await self.incoming.put(
                {"type": "websocket.receive", "text": json.dumps(payload)}
            )

        async def send_text(self, text: str) -> None:
            await self.incoming.put({"type": "websocket.receive", "text": text})

        async def receive_json(self) -> dict:
            event = await self.outgoing.get()
            self.assert_send_event(event)
            return json.loads(event["text"])

        @staticmethod
        def assert_send_event(event: dict) -> None:
            if event["type"] != "websocket.send":
                raise AssertionError(f"Expected send, received {event!r}")

        async def disconnect(self) -> None:
            await self.incoming.put({"type": "websocket.disconnect", "code": 1000})
            if self.task is not None:
                await self.task

    async def asyncSetUp(self) -> None:
        self.runtime = self.FakeRuntime()
        self.application = create_app(runtime=self.runtime)
        self.socket = self.WebSocketHarness(self.application)
        await self.socket.connect()

    async def asyncTearDown(self) -> None:
        if self.socket.task is not None and not self.socket.task.done():
            await self.socket.disconnect()

    async def test_route_is_registered(self) -> None:
        websocket_route = next(
            (
                route
                for route in websocket_router.routes
                if isinstance(route, APIWebSocketRoute)
                and route.path == "/ws/chat"
            ),
            None,
        )

        self.assertIsNotNone(
            websocket_route,
            "Expected an APIWebSocketRoute registered at /ws/chat.",
        )
        self.assertEqual(
            str(self.application.url_path_for(websocket_route.name)),
            "/ws/chat",
        )

    async def test_successful_request_uses_shared_agent_loop(self) -> None:
        await self.socket.send_json({"message": "Analyze performance", "agent_id": "AGT001"})
        event = await self.socket.receive_json()

        self.assertEqual(event["type"], "response")
        self.assertEqual(event["content"], "Fake agent answer")
        self.assertTrue(event["session_id"].startswith("ws:"))
        self.assertTrue(event["turn_id"].startswith("turn:"))
        self.assertEqual(
            self.runtime.agent_loop.calls,
            [
                {
                    "content": "Analyze performance",
                    "session_key": event["session_id"],
                    "channel": "websocket",
                    "chat_id": "AGT001",
                }
            ],
        )

    async def test_explicit_identifiers_are_preserved(self) -> None:
        await self.socket.send_json(
            {
                "message": "Hello",
                "agent_id": "AGT001",
                "session_id": "ws:fixed",
                "turn_id": "turn:fixed",
            }
        )
        event = await self.socket.receive_json()

        self.assertEqual(event["session_id"], "ws:fixed")
        self.assertEqual(event["turn_id"], "turn:fixed")

    async def test_invalid_json_returns_safe_error(self) -> None:
        await self.socket.send_text("{")

        self.assertEqual(
            await self.socket.receive_json(),
            {"type": "error", "content": "Invalid JSON payload."},
        )

    async def test_empty_message_preserves_valid_turn_id(self) -> None:
        await self.socket.send_json(
            {"message": " ", "agent_id": "AGT001", "turn_id": "turn:known"}
        )

        self.assertEqual(
            await self.socket.receive_json(),
            {
                "type": "error",
                "content": "message must be a non-empty string.",
                "turn_id": "turn:known",
            },
        )

    async def test_missing_agent_id_returns_error(self) -> None:
        await self.socket.send_json({"message": "Hello"})
        event = await self.socket.receive_json()

        self.assertEqual(event["type"], "error")
        self.assertEqual(event["content"], "agent_id must be a non-empty string.")

    async def test_invalid_identifier_returns_error(self) -> None:
        await self.socket.send_json(
            {"message": "Hello", "agent_id": "AGT001", "session_id": 3}
        )
        event = await self.socket.receive_json()

        self.assertEqual(event["type"], "error")
        self.assertEqual(event["content"], "session_id must be a non-empty string.")

    async def test_unavailable_runtime_returns_error(self) -> None:
        self.runtime.is_running = False
        await self.socket.send_json({"message": "Hello", "agent_id": "AGT001"})
        event = await self.socket.receive_json()

        self.assertEqual(event["type"], "error")
        self.assertEqual(event["content"], "Agent runtime is unavailable.")
        self.assertEqual(self.runtime.agent_loop.calls, [])

    async def test_agent_error_is_sanitized(self) -> None:
        self.runtime.agent_loop.error = RuntimeError("provider key secret-value")
        await self.socket.send_json({"message": "Hello", "agent_id": "AGT001"})
        event = await self.socket.receive_json()

        self.assertEqual(event["type"], "error")
        self.assertEqual(event["content"], "Unable to process the message.")
        self.assertNotIn("secret-value", json.dumps(event))

    async def test_none_agent_result_returns_error(self) -> None:
        self.runtime.agent_loop.result = None
        await self.socket.send_json({"message": "Hello", "agent_id": "AGT001"})
        event = await self.socket.receive_json()

        self.assertEqual(event["type"], "error")
        self.assertEqual(event["content"], "Agent returned no response.")

    async def test_multiple_messages_reuse_connection_session(self) -> None:
        await self.socket.send_json({"message": "First", "agent_id": "AGT001"})
        first = await self.socket.receive_json()
        await self.socket.send_json({"message": "Second", "agent_id": "AGT001"})
        second = await self.socket.receive_json()

        self.assertEqual(first["session_id"], second["session_id"])
        self.assertNotEqual(first["turn_id"], second["turn_id"])
        self.assertEqual(len(self.runtime.agent_loop.calls), 2)

    async def test_normal_client_disconnect_finishes_connection_task(self) -> None:
        await self.socket.disconnect()

        self.assertIsNotNone(self.socket.task)
        self.assertTrue(self.socket.task.done())
        self.assertIsNone(self.socket.task.exception())


if __name__ == "__main__":
    unittest.main()
