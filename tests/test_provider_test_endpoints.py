"""Offline tests for allowlist-only provider connectivity endpoints."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.requests import Request

from admin.db import Base, get_db
from admin.models.config import SystemConfig
from admin.models.model_config import ModelConfig
from admin.models.tenant import Tenant
from admin.models.user import Role, User
from admin.services.auth_service import create_access_token, hash_password
from admin.services.crypto_service import encrypt
from admin.services.provider_test_service import (
    ProviderResponse,
    ProviderTestService,
    ResponseTooLargeError,
    HttpxProviderTransport,
    get_provider_test_service,
)
from api.server import create_app


class RecordingTransport:
    def __init__(self, response: ProviderResponse | None = None, error: Exception | None = None) -> None:
        self.response = response or ProviderResponse(200, b"{}")
        self.error = error
        self.calls: list[tuple[str, dict[str, str], bytes]] = []

    async def post(self, url: str, headers: dict[str, str], body: bytes) -> ProviderResponse:
        self.calls.append((url, headers, body))
        if self.error is not None:
            raise self.error
        return self.response


class ClosableRecordingTransport(RecordingTransport):
    def __init__(self) -> None:
        super().__init__()
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class StubRuntime:
    is_running = False

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None


class ByteChunks(httpx.AsyncByteStream):
    def __init__(self, chunks: tuple[bytes, ...], gate: asyncio.Event | None = None) -> None:
        self._chunks = chunks
        self._gate = gate

    async def __aiter__(self):  # type: ignore[override]
        if self._gate is not None:
            await self._gate.wait()
        for chunk in self._chunks:
            yield chunk

    async def aclose(self) -> None:
        return None


class FailingStream(httpx.AsyncByteStream):
    async def __aiter__(self):  # type: ignore[override]
        raise httpx.ReadError("truncated test response")
        yield b""  # pragma: no cover - establishes this as an async generator

    async def aclose(self) -> None:
        return None


class ProviderTestServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_specific_payloads_and_headers(self) -> None:
        transport = RecordingTransport()
        service = ProviderTestService(transport)
        result = await service.test(
            provider="anthropic", model="claude-test", api_key="credential", base_url="https://api.anthropic.com"
        )
        self.assertTrue(result.ok)
        url, headers, body = transport.calls[0]
        self.assertEqual(url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(headers["x-api-key"], "credential")
        self.assertNotIn("authorization", headers)
        self.assertEqual(json.loads(body)["max_tokens"], 1)

        result = await service.test(
            provider="openrouter", model="openai/gpt-test", api_key="credential", base_url="https://openrouter.ai/api/v1"
        )
        self.assertTrue(result.ok)
        url, headers, body = transport.calls[1]
        self.assertEqual(url, "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(headers["authorization"], "Bearer credential")
        self.assertEqual(json.loads(body)["messages"][0]["content"], "ping")

    async def test_allowlist_rejects_unsafe_or_custom_origins_without_transport(self) -> None:
        transport = RecordingTransport()
        service = ProviderTestService(transport)
        for provider, base_url in (
            ("openai", "http://api.openai.com/v1"),
            ("openai", "https://localhost/v1"),
            ("openai", "https://127.0.0.1/v1"),
            ("openai", "https://169.254.169.254/v1"),
            ("openai", "https://user@api.openai.com/v1"),
            ("openai", "https://api.openai.com:444/v1"),
            ("custom", "https://example.test/v1"),
        ):
            with self.subTest(base_url=base_url):
                result = await service.test(
                    provider=provider, model="gpt-test", api_key="credential", base_url=base_url
                )
                self.assertFalse(result.ok)
                self.assertEqual(result.message, "Provider test configuration is not permitted.")
        result = await service.test(  # type: ignore[arg-type]
            provider="openai", model=123, api_key="credential", base_url="https://api.openai.com/v1"
        )
        self.assertFalse(result.ok)
        self.assertEqual(transport.calls, [])

    async def test_redirect_timeout_oversize_and_upstream_errors_are_sanitized(self) -> None:
        cases = (
            RecordingTransport(response=ProviderResponse(302, b"redirect")),
            RecordingTransport(error=asyncio.TimeoutError()),
            RecordingTransport(error=ResponseTooLargeError()),
            RecordingTransport(error=RuntimeError("credential should not appear")),
        )
        for transport in cases:
            result = await ProviderTestService(transport).test(
                provider="openai", model="gpt-test", api_key="credential", base_url="https://api.openai.com/v1"
            )
            self.assertFalse(result.ok)
            self.assertNotIn("credential", result.message)

    async def test_httpx_transport_streams_content_length_and_mock_chunked_responses_without_redirects(self) -> None:
        calls = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if request.url.path == "/redirect":
                return httpx.Response(302, headers={"location": "https://unapproved.example/"})
            if request.url.path == "/chunked":
                # MockTransport does not test wire framing; httpx owns that in
                # production.  This verifies our streaming path consumes it.
                return httpx.Response(200, headers={"transfer-encoding": "chunked"}, stream=ByteChunks((b"{", b"}")))
            return httpx.Response(200, headers={"content-length": "2"}, content=b"{}")

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False, trust_env=False)
        transport = HttpxProviderTransport(client=client)
        try:
            success = await transport.post("https://api.openai.com/v1/chat/completions", {}, b"{}")
            chunked = await transport.post("https://api.openai.com/chunked", {}, b"{}")
            redirect = await transport.post("https://api.openai.com/redirect", {}, b"{}")
        finally:
            await client.aclose()
        self.assertEqual((success.status_code, success.body), (200, b"{}"))
        self.assertEqual((chunked.status_code, chunked.body), (200, b"{}"))
        self.assertEqual(redirect.status_code, 302)
        self.assertEqual(calls, 3)

    async def test_httpx_transport_enforces_total_deadline_and_cancellation_releases_slot(self) -> None:
        started, cancelled = asyncio.Event(), asyncio.Event()

        async def slow_handler(_request: httpx.Request) -> httpx.Response:
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
            raise AssertionError("unreachable")

        client = httpx.AsyncClient(transport=httpx.MockTransport(slow_handler), trust_env=False)
        transport = HttpxProviderTransport(client=client, total_timeout_seconds=0.02, max_concurrent_tests=1)
        try:
            for _ in range(3):
                cancelled.clear()
                with self.assertRaises(asyncio.TimeoutError):
                    await transport.post("https://api.openai.com/v1/chat/completions", {}, b"{}")
                self.assertTrue(cancelled.is_set())
                self.assertEqual(transport._semaphore._value, 1)

            cancelled.clear()
            started.clear()
            task = asyncio.create_task(transport.post("https://api.openai.com/v1/chat/completions", {}, b"{}"))
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(cancelled.is_set())
            self.assertEqual(transport._semaphore._value, 1)
        finally:
            await client.aclose()

    async def test_httpx_transport_bounds_body_and_shared_instance_concurrency(self) -> None:
        gate, active = asyncio.Event(), {"current": 0, "maximum": 0}

        async def handler(_request: httpx.Request) -> httpx.Response:
            active["current"] += 1
            active["maximum"] = max(active["maximum"], active["current"])
            try:
                await gate.wait()
                return httpx.Response(200, stream=ByteChunks((b"{}",)))
            finally:
                active["current"] -= 1

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
        transport = HttpxProviderTransport(client=client, total_timeout_seconds=1)
        try:
            tasks = [asyncio.create_task(transport.post("https://api.openai.com/v1/chat/completions", {}, b"{}")) for _ in range(9)]
            await asyncio.sleep(0)
            self.assertEqual(active["maximum"], 8)
            self.assertFalse(tasks[8].done())
            gate.set()
            await asyncio.gather(*tasks)
        finally:
            await client.aclose()

        oversized_client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, stream=ByteChunks((b"x" * (64 * 1024), b"x")))
            ),
            trust_env=False,
        )
        oversized_transport = HttpxProviderTransport(client=oversized_client)
        try:
            with self.assertRaises(ResponseTooLargeError):
                await oversized_transport.post("https://api.openai.com/v1/chat/completions", {}, b"{}")
        finally:
            await oversized_client.aclose()

        truncated_client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _request: httpx.Response(200, stream=FailingStream())),
            trust_env=False,
        )
        truncated_transport = HttpxProviderTransport(client=truncated_client)
        try:
            result = await ProviderTestService(truncated_transport).test(
                provider="openai", model="gpt-test", api_key="credential", base_url="https://api.openai.com/v1"
            )
            self.assertFalse(result.ok)
            self.assertEqual(result.message, "Provider connection failed.")
        finally:
            await truncated_client.aclose()

    async def test_default_httpx_client_disables_proxy_inheritance_and_redirects(self) -> None:
        captured: dict[str, object] = {}

        def fake_transport(**kwargs: object) -> httpx.MockTransport:
            captured.update(kwargs)
            return httpx.MockTransport(lambda _request: httpx.Response(200, content=b"{}"))

        with patch("admin.services.provider_test_service.httpx.AsyncHTTPTransport", side_effect=fake_transport):
            transport = HttpxProviderTransport()
            try:
                self.assertFalse(transport._client._trust_env)
                self.assertFalse(transport._client.follow_redirects)
                self.assertEqual(captured["verify"], True)
                self.assertEqual(captured["retries"], 0)
            finally:
                await transport.aclose()

    async def test_application_owns_one_service_for_both_routes_and_closes_it_at_shutdown(self) -> None:
        transport = ClosableRecordingTransport()
        service = ProviderTestService(transport)
        application = create_app(runtime=StubRuntime(), provider_test_service=service)  # type: ignore[arg-type]
        other_transport = ClosableRecordingTransport()
        other_service = ProviderTestService(other_transport)
        other_application = create_app(runtime=StubRuntime(), provider_test_service=other_service)  # type: ignore[arg-type]
        request = Request({"type": "http", "app": application, "headers": []})
        self.assertIs(get_provider_test_service(request), service)
        self.assertIs(application.state.provider_test_service, service)
        self.assertIsNot(other_application.state.provider_test_service, service)
        async with application.router.lifespan_context(application):
            self.assertFalse(transport.closed)
        self.assertTrue(transport.closed)
        async with other_application.router.lifespan_context(other_application):
            self.assertFalse(other_transport.closed)
        self.assertTrue(other_transport.closed)


class ProviderTestEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.previous_environment = os.environ.copy()
        os.environ["ADMIN_SECRET_KEY"] = "provider-test-secret-with-at-least-thirty-two-bytes"
        os.environ["ADMIN_ENCRYPTION_KEY"] = Fernet.generate_key().decode("ascii")
        self.directory = tempfile.TemporaryDirectory()
        database_path = Path(self.directory.name) / "provider-test.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.application = create_app()
        self.transport = RecordingTransport()

        async def test_db():
            async with self.sessions() as session:
                yield session

        self.application.dependency_overrides[get_db] = test_db
        self.application.dependency_overrides[get_provider_test_service] = lambda: ProviderTestService(self.transport)
        self.admin_id, self.tenant_id = await self._add_user("admin")
        self.other_id, self.other_tenant_id = await self._add_user("other")
        self.manager_id, _ = await self._add_user("manager", role_name="agent_manager")
        self.token = create_access_token({"sub": self.admin_id})
        self.other_token = create_access_token({"sub": self.other_id})
        self.manager_token = create_access_token({"sub": self.manager_id})

    async def asyncTearDown(self) -> None:
        self.application.dependency_overrides.clear()
        await self.application.state.provider_test_service.aclose()
        await self.engine.dispose()
        self.directory.cleanup()
        os.environ.clear()
        os.environ.update(self.previous_environment)

    async def _add_user(self, username: str, role_name: str = "admin") -> tuple[str, str]:
        user_id, tenant_id = str(uuid.uuid4()), str(uuid.uuid4())
        async with self.sessions() as session:
            session.add(Tenant(id=tenant_id, slug=f"tenant-{tenant_id}", name=username))
            session.add(
                User(
                    id=user_id,
                    tenant_id=tenant_id,
                    username=username,
                    email=f"{username}@example.test",
                    password_hash=hash_password("not-used"),
                    roles=[Role(id=str(uuid.uuid4()), tenant_id=tenant_id, name=role_name)],
                )
            )
            await session.commit()
        return user_id, tenant_id

    async def _request(self, method: str, path: str, body: dict | None = None, token: str | None = None) -> tuple[int, dict]:
        messages: list[dict] = []
        request_body = b"" if body is None else json.dumps(body).encode("utf-8")
        received = False

        async def receive() -> dict:
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": request_body, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message: dict) -> None:
            messages.append(message)

        headers = [(b"content-type", b"application/json")]
        if token:
            headers.append((b"authorization", f"Bearer {token}".encode("ascii")))
        await self.application(
            {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
             "scheme": "http", "path": path, "raw_path": path.encode("ascii"), "query_string": b"",
             "headers": headers, "client": ("127.0.0.1", 12345), "server": ("testserver", 80)},
            receive, send,
        )
        start = next(message for message in messages if message["type"] == "http.response.start")
        content = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
        return start["status"], json.loads(content)

    async def test_routes_authenticate_and_runtime_test_does_not_persist(self) -> None:
        paths = {
            route.path for included in (getattr(route, "original_router", None) for route in self.application.routes)
            if included is not None for route in included.routes if hasattr(route, "path")
        }
        self.assertIn("/api/config/test", paths)
        self.assertIn("/api/admin/model-configs/{model_id}/test", paths)
        status, body = await self._request("POST", "/api/config/test", {"apiKey": "runtime-key"})
        self.assertEqual((status, body["detail"]["error"]["code"]), (401, "UNAUTHORIZED"))
        status, body = await self._request(
            "POST", "/api/config/test", {"apiKey": "runtime-key"}, self.manager_token
        )
        self.assertEqual((status, body["detail"]["error"]["code"]), (403, "INSUFFICIENT_ROLE"))
        status, body = await self._request(
            "POST", "/api/config/test", {"apiKey": "runtime-key"}, self.token
        )
        self.assertEqual((status, body["ok"]), (200, True))
        self.assertNotIn("runtime-key", json.dumps(body))
        self.assertEqual(self.transport.calls[0][1]["authorization"], "Bearer runtime-key")
        async with self.sessions() as session:
            self.assertEqual((await session.execute(select(ModelConfig))).scalars().all(), [])
            self.assertEqual((await session.execute(select(SystemConfig))).scalars().all(), [])
        self.assertIsNone(self.application.state.runtime)

    async def test_model_test_decrypts_own_credential_and_fails_closed(self) -> None:
        model_id = str(uuid.uuid4())
        async with self.sessions() as session:
            session.add(ModelConfig(
                id=model_id, tenant_id=self.tenant_id, provider="openai", model_id="gpt-test",
                display_name="Test", api_key_encrypted=encrypt("stored-key"), base_url="https://api.openai.com/v1",
            ))
            await session.commit()
        status, body = await self._request("POST", f"/api/admin/model-configs/{model_id}/test", token=self.token)
        self.assertEqual((status, body["ok"]), (200, True))
        self.assertNotIn("stored-key", json.dumps(body))
        self.assertEqual(self.transport.calls[0][1]["authorization"], "Bearer stored-key")
        status, body = await self._request("POST", f"/api/admin/model-configs/{model_id}/test", token=self.other_token)
        self.assertEqual((status, body["detail"]["error"]["code"]), (403, "FORBIDDEN"))

        async with self.sessions() as session:
            row = await session.get(ModelConfig, model_id)
            row.api_key_encrypted = "corrupt"
            await session.commit()
        self.transport.calls.clear()
        status, body = await self._request("POST", f"/api/admin/model-configs/{model_id}/test", token=self.token)
        self.assertEqual((status, body["ok"]), (200, False))
        self.assertNotIn("corrupt", body["message"])
        self.assertEqual(self.transport.calls, [])

        async with self.sessions() as session:
            row = await session.get(ModelConfig, model_id)
            row.api_key_encrypted = None
            await session.commit()
        status, body = await self._request("POST", f"/api/admin/model-configs/{model_id}/test", token=self.token)
        self.assertEqual((status, body["ok"]), (200, False))
        self.assertNotIn("stored-key", body["message"])


if __name__ == "__main__":
    unittest.main()
