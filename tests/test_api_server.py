"""Offline integration tests for the FastAPI application foundation."""

from __future__ import annotations

import json
import unittest

try:
    from api.server import app, create_app
except ModuleNotFoundError as exc:
    app = None
    create_app = None
    IMPORT_ERROR = str(exc)
else:
    IMPORT_ERROR = ""


@unittest.skipUnless(
    create_app is not None,
    f"FastAPI test dependencies are unavailable: {IMPORT_ERROR}",
)
class ApiServerTests(unittest.IsolatedAsyncioTestCase):
    class FakeRuntime:
        """A no-I/O RuntimeState stand-in for lifecycle testing."""

        def __init__(self, *, fail_start: bool = False) -> None:
            self.fail_start = fail_start
            self.running = False
            self.start_calls = 0
            self.stop_calls = 0
            self.provider_calls = 0
            self.api_key = "secret-test-key"

        @property
        def is_running(self) -> bool:
            return self.running

        async def start(self) -> None:
            self.start_calls += 1
            if self.fail_start:
                raise RuntimeError("fake startup failure")
            self.running = True

        async def stop(self) -> None:
            self.stop_calls += 1
            self.running = False

    async def _get_health(self, application):
        """Invoke the ASGI app directly, without an HTTP client or network."""
        messages: list[dict] = []
        request_received = False

        async def receive() -> dict:
            nonlocal request_received
            if not request_received:
                request_received = True
                return {
                    "type": "http.request",
                    "body": b"",
                    "more_body": False,
                }
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
                "path": "/api/health",
                "raw_path": b"/api/health",
                "query_string": b"",
                "headers": [],
                "client": ("127.0.0.1", 12345),
                "server": ("testserver", 80),
            },
            receive,
            send,
        )
        response_start = next(
            message for message in messages if message["type"] == "http.response.start"
        )
        response_body = b"".join(
            message.get("body", b"")
            for message in messages
            if message["type"] == "http.response.body"
        )
        return response_start["status"], json.loads(response_body)

    async def test_application_constructs_without_creating_default_runtime(self) -> None:
        application = create_app()

        self.assertIsNone(application.state.runtime)
        self.assertIsNotNone(application.state.runtime_factory)

    async def test_importable_asgi_app_is_lazy(self) -> None:
        self.assertIsNotNone(app)
        self.assertIsNone(app.state.runtime)

    async def test_health_reports_running_loop_without_secrets(self) -> None:
        runtime = self.FakeRuntime()
        application = create_app(runtime=runtime)

        async with application.router.lifespan_context(application):
            status_code, body = await self._get_health(application)

        self.assertEqual(status_code, 200)
        self.assertEqual(
            body,
            {"status": "ok", "agent_loop": "running"},
        )
        self.assertNotIn("secret-test-key", json.dumps(body))
        self.assertEqual(runtime.provider_calls, 0)

    async def test_health_distinguishes_non_running_loop(self) -> None:
        runtime = self.FakeRuntime()
        application = create_app(runtime=runtime)

        status_code, body = await self._get_health(application)

        self.assertEqual(status_code, 200)
        self.assertEqual(
            body,
            {"status": "ok", "agent_loop": "not_running"},
        )

    async def test_lifespan_starts_and_stops_injected_runtime_once(self) -> None:
        runtime = self.FakeRuntime()
        application = create_app(runtime=runtime)

        async with application.router.lifespan_context(application):
            self.assertEqual(runtime.start_calls, 1)
            self.assertTrue(runtime.running)
            self.assertIs(application.state.runtime, runtime)

        self.assertEqual(runtime.stop_calls, 1)
        self.assertFalse(runtime.running)

    async def test_factory_creates_one_runtime_for_an_application(self) -> None:
        created: list[ApiServerTests.FakeRuntime] = []

        def factory() -> ApiServerTests.FakeRuntime:
            runtime = self.FakeRuntime()
            created.append(runtime)
            return runtime

        application = create_app(runtime_factory=factory)

        async with application.router.lifespan_context(application):
            first_runtime = application.state.runtime
        async with application.router.lifespan_context(application):
            self.assertIs(application.state.runtime, first_runtime)

        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].start_calls, 2)
        self.assertEqual(created[0].stop_calls, 2)

    async def test_startup_failure_propagates_and_runs_cleanup(self) -> None:
        runtime = self.FakeRuntime(fail_start=True)
        application = create_app(runtime=runtime)

        with self.assertRaisesRegex(RuntimeError, "fake startup failure"):
            async with application.router.lifespan_context(application):
                pass

        self.assertEqual(runtime.start_calls, 1)
        self.assertEqual(runtime.stop_calls, 1)


if __name__ == "__main__":
    unittest.main()
