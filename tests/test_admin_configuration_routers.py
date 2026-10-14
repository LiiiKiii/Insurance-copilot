"""Offline integration tests for secure administrative configuration APIs."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from admin.db import Base, get_db
from admin.models.config import SystemConfig
from admin.models.model_config import ModelConfig
from admin.models.tenant import Tenant
from admin.models.user import Role, User
from admin.services.auth_service import create_access_token, hash_password
from admin.services.crypto_service import decrypt
from api.server import create_app


class AdminConfigurationRouterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.environment = patch.dict(os.environ, {}, clear=False)
        self.environment.start()
        os.environ["ADMIN_SECRET_KEY"] = "admin-config-test-secret-with-at-least-thirty-two-bytes"
        os.environ["ADMIN_ENCRYPTION_KEY"] = Fernet.generate_key().decode("ascii")
        self.directory = tempfile.TemporaryDirectory()
        database_path = Path(self.directory.name) / "admin-config.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.application = create_app()

        async def test_db():
            async with self.sessions() as session:
                yield session

        self.application.dependency_overrides[get_db] = test_db
        self.super_id, self.super_tenant = await self._add_user("super", superadmin=True)
        self.admin_a_id, self.tenant_a = await self._add_user("admin-a")
        self.admin_b_id, self.tenant_b = await self._add_user("admin-b")
        self.super_token = create_access_token({"sub": self.super_id})
        self.admin_a_token = create_access_token({"sub": self.admin_a_id})
        self.admin_b_token = create_access_token({"sub": self.admin_b_id})

    async def asyncTearDown(self) -> None:
        self.application.dependency_overrides.clear()
        await self.engine.dispose()
        self.directory.cleanup()
        self.environment.stop()

    async def _add_user(self, username: str, *, superadmin: bool = False) -> tuple[str, str]:
        user_id, tenant_id = str(uuid.uuid4()), str(uuid.uuid4())
        async with self.sessions() as session:
            session.add(Tenant(id=tenant_id, slug=f"tenant-{tenant_id}", name=username))
            role = Role(id=str(uuid.uuid4()), tenant_id=tenant_id, name="admin")
            session.add(
                User(
                    id=user_id,
                    tenant_id=tenant_id,
                    username=username,
                    email=f"{username}@example.test",
                    password_hash=hash_password("not-used"),
                    is_superadmin=superadmin,
                    roles=[role],
                )
            )
            await session.commit()
        return user_id, tenant_id

    async def _request(
        self, method: str, target: str, body: dict | None = None, token: str | None = None
    ) -> tuple[int, dict]:
        path, _, query = target.partition("?")
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
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": method,
                "scheme": "http",
                "path": path,
                "raw_path": path.encode("ascii"),
                "query_string": query.encode("ascii"),
                "headers": headers,
                "client": ("127.0.0.1", 12345),
                "server": ("testserver", 80),
            },
            receive,
            send,
        )
        start = next(message for message in messages if message["type"] == "http.response.start")
        response_body = b"".join(
            message.get("body", b"") for message in messages if message["type"] == "http.response.body"
        )
        return start["status"], json.loads(response_body)

    @staticmethod
    def _model_payload(**overrides: object) -> dict:
        payload: dict[str, object] = {
            "provider": "openai",
            "model_id": "gpt-test",
            "display_name": "Test model",
            "model_type": "llm",
            "category": "chat",
            "enabled": True,
            "is_default": False,
        }
        payload.update(overrides)
        return payload

    async def test_routes_are_registered_and_require_authentication(self) -> None:
        included = [getattr(route, "original_router", None) for route in self.application.routes]
        registered_paths = {
            route.path
            for included_router in included
            if included_router is not None
            for route in included_router.routes
            if hasattr(route, "path")
        }
        self.assertIn("/api/admin/model-configs/", registered_paths)
        self.assertIn("/api/admin/configs/public", registered_paths)
        status, body = await self._request("GET", "/api/admin/model-configs/")
        self.assertEqual((status, body["detail"]["error"]["code"]), (401, "UNAUTHORIZED"))
        status, body = await self._request("GET", "/api/admin/configs/public")
        self.assertEqual((status, body["detail"]["error"]["code"]), (401, "UNAUTHORIZED"))

    async def test_model_crud_redacts_credentials_and_enforces_tenant_scope(self) -> None:
        status, body = await self._request(
            "POST",
            "/api/admin/model-configs/",
            self._model_payload(tenant_id=self.tenant_a, api_key="provider-secret"),
            self.super_token,
        )
        self.assertEqual(status, 200)
        model = body["data"]
        self.assertTrue(model["has_api_key"])
        self.assertNotIn("api_key", model)
        self.assertNotIn("api_key_encrypted", model)
        model_id = model["id"]
        async with self.sessions() as session:
            encrypted = (await session.get(ModelConfig, model_id)).api_key_encrypted
        self.assertNotEqual(encrypted, "provider-secret")
        self.assertEqual(decrypt(encrypted), "provider-secret")

        status, _ = await self._request("GET", f"/api/admin/model-configs/{model_id}", token=self.admin_a_token)
        self.assertEqual(status, 200)
        status, body = await self._request("GET", f"/api/admin/model-configs/{model_id}", token=self.admin_b_token)
        self.assertEqual((status, body["detail"]["error"]["code"]), (403, "FORBIDDEN"))
        status, body = await self._request(
            "PUT", f"/api/admin/model-configs/{model_id}", {"display_name": "Updated", "api_key": ""}, self.admin_a_token
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["display_name"], "Updated")
        async with self.sessions() as session:
            self.assertEqual(decrypt((await session.get(ModelConfig, model_id)).api_key_encrypted), "provider-secret")

        status, global_body = await self._request(
            "POST", "/api/admin/model-configs/", self._model_payload(model_id="global", tenant_id=None), self.super_token
        )
        self.assertEqual(status, 200)
        status, body = await self._request(
            "PUT", f"/api/admin/model-configs/{global_body['data']['id']}", {"display_name": "Denied"}, self.admin_a_token
        )
        self.assertEqual((status, body["detail"]["error"]["code"]), (403, "FORBIDDEN"))
        status, _ = await self._request(
            "PUT", f"/api/admin/model-configs/{model_id}", {"tenant_id": self.tenant_b}, self.admin_a_token
        )
        self.assertEqual(status, 422)
        status, body = await self._request("DELETE", f"/api/admin/model-configs/{model_id}", token=self.admin_a_token)
        self.assertEqual((status, body["detail"]["error"]["code"]), (403, "INSUFFICIENT_ROLE"))
        status, _ = await self._request("DELETE", f"/api/admin/model-configs/{model_id}", token=self.super_token)
        self.assertEqual(status, 200)

    async def test_default_switching_and_toggle_are_deterministic(self) -> None:
        status, first = await self._request(
            "POST", "/api/admin/model-configs/", self._model_payload(model_id="first", is_default=True), self.super_token
        )
        self.assertEqual(status, 200)
        status, second = await self._request(
            "POST", "/api/admin/model-configs/", self._model_payload(model_id="second", category="multimodal", is_default=True), self.super_token
        )
        self.assertEqual(status, 200)
        first_id, second_id = first["data"]["id"], second["data"]["id"]
        status, body = await self._request("GET", "/api/admin/model-configs/defaults?model_type=llm", token=self.super_token)
        self.assertEqual((status, [row["id"] for row in body["data"]]), (200, [second_id]))
        status, _ = await self._request("POST", f"/api/admin/model-configs/{first_id}/set-default", token=self.super_token)
        self.assertEqual(status, 200)
        status, _ = await self._request("PUT", f"/api/admin/model-configs/{first_id}/set-default", token=self.super_token)
        self.assertEqual(status, 200)
        status, _ = await self._request("POST", f"/api/admin/model-configs/{first_id}/toggle-active", token=self.super_token)
        self.assertEqual(status, 200)
        status, body = await self._request("GET", "/api/admin/model-configs/defaults?model_type=llm", token=self.super_token)
        self.assertEqual((status, body["data"]), (200, []))

    async def test_config_scope_public_filter_secret_rejection_and_cache_invalidation(self) -> None:
        with patch("admin.routers.config.invalidate") as invalidate:
            status, global_config = await self._request(
                "POST",
                "/api/admin/configs/",
                {"config_key": "ui.title", "config_value": "Global", "is_public": True},
                self.super_token,
            )
            self.assertEqual(status, 200)
            invalidate.assert_called_once_with("ui.title")
        config_id = global_config["data"]["id"]
        status, _ = await self._request(
            "POST",
            "/api/admin/configs/",
            {"config_key": "ui.title", "config_value": "Tenant A", "tenant_id": self.tenant_a},
            self.super_token,
        )
        self.assertEqual(status, 200)
        status, body = await self._request("GET", "/api/admin/configs/", token=self.admin_a_token)
        self.assertEqual((status, len(body["data"])), (200, 2))
        status, body = await self._request("GET", "/api/admin/configs/ui.title", token=self.admin_a_token)
        self.assertEqual((status, body["data"]["config_value"]), (200, "Tenant A"))
        status, body = await self._request("GET", "/api/admin/configs/ui.title", token=self.admin_b_token)
        self.assertEqual((status, body["data"]["config_value"]), (200, "Global"))
        status, body = await self._request("GET", f"/api/admin/configs/ui.title?tenant_id={self.tenant_a}", token=self.admin_b_token)
        self.assertEqual((status, body["detail"]["error"]["code"]), (403, "FORBIDDEN"))
        status, body = await self._request("GET", "/api/admin/configs/public", token=self.admin_a_token)
        self.assertEqual((status, body["data"]), (200, {"ui.title": "Global"}))
        status, body = await self._request(
            "POST", "/api/admin/configs/", {"config_key": "provider.api_key", "config_value": "secret"}, self.super_token
        )
        self.assertEqual((status, body["detail"]["error"]["code"]), (422, "INVALID_CONFIG_KEY"))
        with patch("admin.routers.config.invalidate") as invalidate:
            status, body = await self._request(
                "POST", "/api/admin/configs/", {"config_key": "ui.title", "config_value": "duplicate"}, self.super_token
            )
            self.assertEqual((status, body["detail"]["error"]["code"]), (409, "CONFLICT"))
            invalidate.assert_not_called()
            status, _ = await self._request(
                "PUT", f"/api/admin/configs/{config_id}", {"config_value": "Changed"}, self.super_token
            )
            self.assertEqual(status, 200)
            invalidate.assert_called_once_with("ui.title")
        with patch("admin.routers.config.invalidate") as invalidate:
            status, _ = await self._request("DELETE", f"/api/admin/configs/{config_id}", token=self.super_token)
            self.assertEqual(status, 200)
            invalidate.assert_called_once_with("ui.title")
        status, body = await self._request("GET", "/api/admin/configs/ui.title", token=self.super_token)
        self.assertEqual((status, body["detail"]["error"]["code"]), (404, "NOT_FOUND"))

    async def test_provider_test_endpoint_is_deferred_and_no_network_is_performed(self) -> None:
        status, body = await self._request("POST", "/api/admin/model-configs/not-real/test", token=self.admin_a_token)
        self.assertEqual(status, 404)
        self.assertEqual(body["detail"], "Not Found")

    async def test_failed_commit_rolls_back_without_invalidating_cache(self) -> None:
        observed = {"rolled_back": False}

        class CommitFailureSession:
            def __init__(self, session: AsyncSession) -> None:
                self.session = session

            async def execute(self, *args, **kwargs):
                return await self.session.execute(*args, **kwargs)

            async def get(self, *args, **kwargs):
                return await self.session.get(*args, **kwargs)

            def add(self, instance) -> None:
                self.session.add(instance)

            async def commit(self) -> None:
                raise SQLAlchemyError("commit unavailable")

            async def rollback(self) -> None:
                observed["rolled_back"] = True
                await self.session.rollback()

        async def failing_db():
            async with self.sessions() as session:
                yield CommitFailureSession(session)

        self.application.dependency_overrides[get_db] = failing_db
        with patch("admin.routers.config.invalidate") as invalidate:
            status, body = await self._request(
                "POST",
                "/api/admin/configs/",
                {"config_key": "ui.commit_failure", "config_value": "value"},
                self.super_token,
            )
        self.assertEqual((status, body["detail"]["error"]["code"]), (503, "DATABASE_UNAVAILABLE"))
        self.assertTrue(observed["rolled_back"])
        invalidate.assert_not_called()
        async with self.sessions() as session:
            self.assertIsNone(
                (
                    await session.execute(
                        select(SystemConfig).where(SystemConfig.config_key == "ui.commit_failure")
                    )
                ).scalar_one_or_none()
            )


if __name__ == "__main__":
    unittest.main()
