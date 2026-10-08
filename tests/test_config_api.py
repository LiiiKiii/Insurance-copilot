"""Offline integration tests for the read-only configuration status API."""

from __future__ import annotations

import json
import unittest

try:
    from api.routers.config import router as config_router
    from api.server import app, create_app
    from fastapi.routing import APIRoute
except ModuleNotFoundError as exc:
    app = None
    create_app = None
    config_router = None
    APIRoute = None
    IMPORT_ERROR = str(exc)
else:
    IMPORT_ERROR = ""


@unittest.skipUnless(
    create_app is not None,
    f"FastAPI test dependencies are unavailable: {IMPORT_ERROR}",
)
class ConfigApiTests(unittest.IsolatedAsyncioTestCase):
    class FakeRuntime:
        """Runtime double that records whether endpoint handling touches it."""

        def __init__(self, *, running: bool = False) -> None:
            self.running = running
            self.provider_calls = 0
            self.api_key = "secret-test-key"
            self.api_base = "https://secret.example/v1"
            self.model = "secret-model"

        @property
        def is_running(self) -> bool:
            return self.running

        async def start(self) -> None:
            self.running = True

        async def stop(self) -> None:
            self.running = False

    async def _get(self, application, path: str) -> tuple[int, dict]:
        messages: list[dict] = []
        received = False

        async def receive() -> dict:
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": b"", "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message: dict) -> None:
            messages.append(message)

        await application(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "headers": [],
                "client": ("127.0.0.1", 12345),
                "server": ("testserver", 80),
            },
            receive,
            send,
        )

        status = next(message for message in messages if message["type"] == "http.response.start")
        body = b"".join(
            message.get("body", b"")
            for message in messages
            if message["type"] == "http.response.body"
        )
        return status["status"], json.loads(body)

    async def test_route_is_registered_on_factory_and_importable_app(self) -> None:
        application = create_app()
        route = next(
            (
                route
                for route in config_router.routes
                if isinstance(route, APIRoute) and route.path == "/api/config/status"
            ),
            None,
        )

        self.assertIsNotNone(route)
        self.assertEqual(route.methods, {"GET"})
        self.assertIsNotNone(app)
        self.assertEqual(
            str(app.url_path_for(route.name)),
            "/api/config/status",
        )

    async def test_running_runtime_reports_exact_configured_response_without_leaks(self) -> None:
        runtime = self.FakeRuntime(running=True)
        status, body = await self._get(create_app(runtime=runtime), "/api/config/status")

        self.assertEqual(status, 200)
        self.assertEqual(body, {"ok": True, "configured": True})
        self.assertEqual(set(body), {"ok", "configured"})
        self.assertTrue(all(isinstance(value, bool) for value in body.values()))
        self.assertNotIn("secret-test-key", json.dumps(body))
        self.assertNotIn("secret.example", json.dumps(body))
        self.assertNotIn("secret-model", json.dumps(body))
        self.assertEqual(runtime.provider_calls, 0)

    async def test_not_started_missing_stopped_and_failed_runtimes_report_false(self) -> None:
        cases = (
            ("not_started", create_app(runtime=self.FakeRuntime(running=False))),
            ("missing", create_app()),
            ("stopped_or_failed", create_app(runtime=self.FakeRuntime(running=False))),
        )

        for label, application in cases:
            with self.subTest(label=label):
                status, body = await self._get(application, "/api/config/status")
                self.assertEqual(status, 200)
                self.assertEqual(body, {"ok": True, "configured": False})

    async def test_factory_created_runtime_is_reflected_without_endpoint_creation(self) -> None:
        created: list[ConfigApiTests.FakeRuntime] = []

        def factory() -> ConfigApiTests.FakeRuntime:
            runtime = self.FakeRuntime()
            created.append(runtime)
            return runtime

        application = create_app(runtime_factory=factory)
        self.assertEqual(created, [])

        async with application.router.lifespan_context(application):
            status, body = await self._get(application, "/api/config/status")
            self.assertEqual((status, body), (200, {"ok": True, "configured": True}))
            self.assertEqual(len(created), 1)
            self.assertEqual(created[0].provider_calls, 0)

    async def test_health_endpoint_contract_remains_unchanged(self) -> None:
        runtime = self.FakeRuntime(running=True)
        status, body = await self._get(create_app(runtime=runtime), "/api/health")

        self.assertEqual(status, 200)
        self.assertEqual(body, {"status": "ok", "agent_loop": "running"})


if __name__ == "__main__":
    unittest.main()
