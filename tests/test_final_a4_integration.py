"""A4 global Apply authorization and route composition checks."""
from __future__ import annotations

import unittest
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from admin.db import get_db
from admin.dependencies import get_current_user
from api.server import create_app


class FinalA4IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = create_app(runtime=SimpleNamespace(is_running=True))
        self.app.dependency_overrides[get_db] = lambda: object()
        self.current = SimpleNamespace(is_superadmin=False, tenant_id="tenant-a", username="alice", roles=[
            SimpleNamespace(name="admin", tenant_id="tenant-a")
        ])
        self.app.dependency_overrides[get_current_user] = lambda: self.current
        self.audit_patch = patch("admin.middleware.audit_middleware._write_log_sync")
        self.audit_patch.start()

    async def asyncTearDown(self):
        self.audit_patch.stop()
        self.app.dependency_overrides.clear()

    async def test_tenant_admin_cannot_apply_global_runtime_or_credentials(self):
        with patch("api.routers.config.build_candidate") as build, patch("api.routers.config.persist_runtime_config", new_callable=AsyncMock) as persist:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test") as client:
                response = await client.post("/api/config/apply", json={"apiKey": "tenant-key", "provider": "openrouter", "model": "model"})
        self.assertEqual(response.status_code, 403)
        build.assert_not_called()
        persist.assert_not_awaited()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test") as client:
            feature_update = await client.post("/api/feature-models", json={"slug": "general", "model": "model"})
            feature_reset = await client.post("/api/feature-models/reset")
        self.assertEqual((feature_update.status_code, feature_reset.status_code), (403, 403))

    async def test_superadmin_can_apply_through_existing_candidate_path(self):
        self.current = SimpleNamespace(is_superadmin=True, tenant_id="tenant-a", roles=[])
        candidate = object()

        async def replace(app, value, *, before_publish, on_unpublished_failure):
            self.assertIs(value, candidate)
            await before_publish()
            return True

        self.app.state.runtime_apply_coordinator = SimpleNamespace(replace=AsyncMock(side_effect=replace))
        with patch("api.routers.config.build_candidate", return_value=candidate) as build, patch("api.routers.config.persist_runtime_config", new_callable=AsyncMock) as persist:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test") as client:
                response = await client.post("/api/config/apply", json={"apiKey": "platform-key", "provider": "openrouter", "model": "model"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        build.assert_called_once()
        persist.assert_awaited_once()

    async def test_a4_routes_and_deferred_briefing_are_explicit(self):
        paths = self.app.openapi()["paths"]
        for path, method in (
            ("/api/admin/auth/login", "POST"),
            ("/api/admin/model-configs/", "GET"),
            ("/api/admin/configs/", "GET"),
            ("/api/admin/logs/requests", "GET"),
            ("/api/admin/logs/ai-audit", "GET"),
            ("/api/admin/logs/errors", "GET"),
            ("/api/config/status", "GET"),
            ("/api/config/apply", "POST"),
            ("/api/feature-models", "GET"),
            ("/api/health", "GET"),
            ("/api/planning/chase-plan", "POST"),
        ):
            self.assertIn(method.lower(), paths[path])
        self.assertEqual(str(self.app.url_path_for("chat")), "/ws/chat")
        self.assertNotIn("/api/briefing/today", paths)
        self.assertNotIn("/api/chat", paths)

    async def test_planning_requires_live_identity_and_own_agent_id(self):
        tool = SimpleNamespace(execute=AsyncMock(return_value=json.dumps({"agent_id": "alice", "weekly_plans": []})))
        with patch("api.routers.planning._build_chase_plan_tool", return_value=tool) as build:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test") as client:
                spoof = await client.post("/api/planning/chase-plan", json={"agent_id": "bob"})
                own = await client.post("/api/planning/chase-plan", json={"agent_id": "alice"})
                self.app.dependency_overrides.pop(get_current_user)
                anonymous = await client.post("/api/planning/chase-plan", json={"agent_id": "alice"})
        self.assertEqual(spoof.status_code, 403)
        self.assertEqual(own.status_code, 200)
        self.assertEqual(own.json()["agent_id"], "alice")
        self.assertEqual(anonymous.status_code, 401)
        build.assert_called_once()
        tool.execute.assert_awaited_once()
