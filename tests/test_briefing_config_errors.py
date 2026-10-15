"""Offline ASGI tests for briefing model-configuration failures."""

from __future__ import annotations

import json
import os
import unittest
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

from cryptography.fernet import Fernet
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from admin.config_bridge import DefaultModelConfigurationError
from admin.db import Base
from admin.models.inbox import DailyBriefing, InboxMessage  # noqa: F401 -- metadata
from admin.models.model_config import ModelConfig
from admin.models.tenant import Tenant
from admin.models.user import User
from admin.services.crypto_service import encrypt
from api.routers.briefing import (
    MODEL_CONFIGURATION_UNAVAILABLE,
    _generate_and_save,
    router as briefing_router,
)


class BriefingConfigurationErrorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.environment = patch.dict(os.environ, {}, clear=False)
        self.environment.start()
        for name in (
            "ADMIN_ENCRYPTION_KEY",
            "OPENROUTER_API_KEY",
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
        ):
            os.environ.pop(name, None)

        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)
        self._seed_agent()

        self.router_db = patch("api.routers.briefing.get_sync_db", self._get_sync_db)
        self.bridge_db = patch("admin.db.get_sync_db", self._get_sync_db)
        self.router_db.start()
        self.bridge_db.start()

        self.application = FastAPI()
        self.application.include_router(briefing_router)

    async def asyncTearDown(self) -> None:
        self.bridge_db.stop()
        self.router_db.stop()
        self.engine.dispose()
        self.environment.stop()

    @contextmanager
    def _get_sync_db(self):
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _seed_agent(self) -> None:
        with self.session_factory.begin() as session:
            session.add(Tenant(id="tenant-a", slug="tenant-a", name="Tenant A"))
            session.add(
                User(
                    id="user-a",
                    tenant_id="tenant-a",
                    username="agent-a",
                    email="agent-a@example.test",
                    password_hash="not-used-by-this-route",
                )
            )

    def _add_global_model(self, **overrides: object) -> None:
        values: dict[str, object] = {
            "id": "global-default",
            "tenant_id": None,
            "provider": "openrouter",
            "model_id": "test-model",
            "display_name": "Test Model",
            "model_type": "llm",
            "api_key_encrypted": None,
            "base_url": "https://provider.invalid/v1",
            "max_tokens": 128,
            "temperature": 0.1,
            "enabled": True,
            "is_default": True,
        }
        values.update(overrides)
        with self.session_factory.begin() as session:
            session.add(ModelConfig(**values))

    async def _request_regenerate(self) -> tuple[int, dict]:
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

        path = "/api/briefing/today/regenerate"
        await self.application(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode("ascii"),
                "query_string": b"agent_id=agent-a",
                "headers": [],
                "client": ("127.0.0.1", 12345),
                "server": ("testserver", 80),
            },
            receive,
            send,
        )
        start = next(message for message in messages if message["type"] == "http.response.start")
        body = b"".join(
            message.get("body", b"")
            for message in messages
            if message["type"] == "http.response.body"
        )
        return start["status"], json.loads(body)

    def _assert_configuration_error(self, status: int, body: dict) -> None:
        self.assertEqual(status, 503)
        self.assertEqual(
            body,
            {
                "detail": {
                    "error": {
                        "code": MODEL_CONFIGURATION_UNAVAILABLE,
                        "message": "Model configuration is unavailable.",
                    }
                }
            },
        )

    async def test_missing_default_model_retains_rule_based_fallback(self) -> None:
        status, body = await self._request_regenerate()

        self.assertEqual(status, 200)
        self.assertEqual(body["briefing"]["model_display_name"], "fallback-rule-based")

    async def test_database_unavailable_result_retains_rule_based_fallback(self) -> None:
        with patch(
            "admin.db.get_sync_db",
            side_effect=OperationalError("select", {}, None),
        ):
            status, body = await self._request_regenerate()

        self.assertEqual(status, 200)
        self.assertEqual(body["briefing"]["model_display_name"], "fallback-rule-based")

    async def test_invalid_ciphertext_returns_sanitized_503_without_provider_use(self) -> None:
        ciphertext = "invalid-fernet-ciphertext"
        self._add_global_model(api_key_encrypted=ciphertext)
        os.environ["OPENROUTER_API_KEY"] = "must-not-be-used"

        with patch(
            "api.briefing.llm_generator._call_openai_compat",
            new_callable=AsyncMock,
        ) as provider:
            status, body = await self._request_regenerate()

        self._assert_configuration_error(status, body)
        provider.assert_not_awaited()
        rendered = json.dumps(body)
        for forbidden in (ciphertext, "must-not-be-used", "OperationalError"):
            self.assertNotIn(forbidden, rendered)

    async def test_missing_encryption_key_returns_sanitized_503(self) -> None:
        key = Fernet.generate_key().decode("ascii")
        os.environ["ADMIN_ENCRYPTION_KEY"] = key
        ciphertext = encrypt("stored-key")
        os.environ.pop("ADMIN_ENCRYPTION_KEY")
        self._add_global_model(api_key_encrypted=ciphertext)

        status, body = await self._request_regenerate()

        self._assert_configuration_error(status, body)
        self.assertNotIn(ciphertext, json.dumps(body))

    async def test_duplicate_global_defaults_return_sanitized_503(self) -> None:
        self._add_global_model(id="global-a")
        self._add_global_model(id="global-b")

        status, body = await self._request_regenerate()

        self._assert_configuration_error(status, body)

    async def test_successful_empty_briefing_keeps_existing_model_contract(self) -> None:
        self._add_global_model()
        os.environ["OPENROUTER_API_KEY"] = "configured-but-unused"

        status, body = await self._request_regenerate()

        self.assertEqual(status, 200)
        self.assertEqual(body["briefing"]["model_id"], "global-default")
        self.assertEqual(body["briefing"]["model_display_name"], "Test Model")

    async def test_unrelated_generation_error_is_not_mapped_to_configuration_error(self) -> None:
        with patch(
            "api.routers.briefing.generate_briefing",
            side_effect=RuntimeError("unrelated failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "unrelated failure"):
                await _generate_and_save("tenant-a", "agent-a", [])


if __name__ == "__main__":
    unittest.main()
