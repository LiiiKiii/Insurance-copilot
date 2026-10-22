"""Offline HTTP contracts for tenant-scoped business and compatibility routes."""

from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import httpx
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from admin.db import Base, get_db
from admin.models.chat import ChatMessage, ChatSession
from admin.models.competition import Competition, CompetitionEntry
from admin.models.inbox import InboxMessage
from admin.models.performance_target import PerformanceTarget
from admin.models.tenant import Tenant
from admin.models.user import Role, User
from admin.services.auth_service import create_access_token
from api.server import create_app


class ApiEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.environment = patch.dict(
            os.environ,
            {"ADMIN_SECRET_KEY": "a5-api-test-secret-with-at-least-thirty-two-bytes"},
        )
        self.environment.start()
        self.audit_patch = patch("admin.middleware.audit_middleware._write_log_sync")
        self.audit_patch.start()
        self.directory = tempfile.TemporaryDirectory()
        database_path = Path(self.directory.name) / "api-endpoints.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
        self.sync_engine = create_engine(f"sqlite:///{database_path.as_posix()}")
        self.sync_sessions = sessionmaker(self.sync_engine, expire_on_commit=False)
        self.sessions = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        self.app = create_app()

        async def test_db():
            async with self.sessions() as session:
                yield session

        self.app.dependency_overrides[get_db] = test_db
        self.briefing_db_patch = patch("api.routers.briefing.get_sync_db", self._sync_test_db)
        self.briefing_db_patch.start()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test"
        )

        async with self.sessions() as session:
            for tenant_id in ("tenant-a", "tenant-b"):
                session.add(Tenant(id=tenant_id, slug=tenant_id, name=tenant_id))
            for user_id, tenant_id, role_name in (
                ("admin-a", "tenant-a", "admin"),
                ("reader-b", "tenant-b", "readonly"),
            ):
                role = Role(id=f"role-{user_id}", tenant_id=tenant_id, name=role_name)
                session.add(
                    User(
                        id=user_id,
                        tenant_id=tenant_id,
                        username=user_id,
                        email=f"{user_id}@example.test",
                        password_hash="unused-in-token-tests",
                        roles=[role],
                    )
                )
            for user_id, tenant_id, active in (
                ("agent-a", "tenant-a", True),
                ("inactive-a", "tenant-a", False),
                ("agent-b", "tenant-b", True),
            ):
                session.add(User(
                    id=user_id,
                    tenant_id=tenant_id,
                    username=user_id,
                    email=f"{user_id}@example.test",
                    password_hash="unused-in-token-tests",
                    is_active=active,
                ))
            session.add_all(
                [
                    PerformanceTarget(
                        id=f"target-{suffix}",
                        tenant_id=f"tenant-{suffix}",
                        agent_id="shared-agent",
                        metric_key="premium",
                        target_value=1000 if suffix == "a" else 9000,
                        period_start="2026-01-01",
                        period_end="2026-12-31",
                    )
                    for suffix in ("a", "b")
                ]
            )
            session.add_all(
                [
                    Competition(
                        id=f"competition-{suffix}",
                        tenant_id=f"tenant-{suffix}",
                        name=f"Contest {suffix}",
                        type="competition",
                        target_metric="premium",
                        target_value=1000,
                        deadline=(date.today() + timedelta(days=10)).isoformat(),
                    )
                    for suffix in ("a", "b")
                ]
            )
            session.add_all(
                [
                    CompetitionEntry(
                        id=f"entry-{suffix}",
                        competition_id=f"competition-{suffix}",
                        agent_id="admin-a" if suffix == "a" else "reader-b",
                        current_value=500,
                        gap=500,
                        status="active",
                    )
                    for suffix in ("a", "b")
                ]
            )
            session.add(
                ChatSession(
                    id="ws:session-a",
                    tenant_id="tenant-a",
                    user_id="admin-a",
                    agent_id="admin-a",
                    title="Persisted chat",
                    message_count=2,
                    messages=[
                        ChatMessage(role="user", content="Hello"),
                        ChatMessage(role="assistant", content="Hi"),
                    ],
                )
            )
            session.add_all([
                InboxMessage(
                    id=f"message-{suffix}",
                    tenant_id=f"tenant-{suffix}",
                    agent_id="admin-a" if suffix == "a" else "reader-b",
                    external_id=f"external-{suffix}",
                    priority="P1",
                    category="follow-up",
                    notification_name=f"Notification {suffix}",
                    receiver_type="agent",
                    raw_content=f"private {suffix}",
                )
                for suffix in ("a", "b")
            ])
            await session.commit()

        self.admin_headers = {
            "Authorization": f"Bearer {create_access_token({'sub': 'admin-a'})}"
        }
        self.reader_headers = {
            "Authorization": f"Bearer {create_access_token({'sub': 'reader-b'})}"
        }

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.briefing_db_patch.stop()
        self.app.dependency_overrides.clear()
        await self.engine.dispose()
        self.sync_engine.dispose()
        self.directory.cleanup()
        self.audit_patch.stop()
        self.environment.stop()

    @contextmanager
    def _sync_test_db(self):
        with self.sync_sessions.begin() as session:
            yield session

    async def test_health_is_public_and_reports_lazy_runtime(self) -> None:
        response = await self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "agent_loop": "not_started"})

    async def test_agents_list_matches_frontend_shape_and_tenant_scope(self) -> None:
        anonymous = await self.client.get("/api/agents-list")
        tenant_a = await self.client.get("/api/agents-list", headers=self.admin_headers)
        tenant_b = await self.client.get("/api/agents-list", headers=self.reader_headers)

        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(tenant_a.status_code, 200)
        self.assertEqual(tenant_a.json(), {
            "ok": True,
            "data": [{"agent_id": "admin-a"}, {"agent_id": "agent-a"}],
        })
        self.assertEqual(tenant_b.status_code, 200)
        self.assertEqual(tenant_b.json(), {
            "ok": True,
            "data": [{"agent_id": "agent-b"}, {"agent_id": "reader-b"}],
        })

    async def test_compatibility_business_reads_match_frontend_contracts(self) -> None:
        paths = self.app.openapi()["paths"]
        for path in (
            "/api/agent-info",
            "/api/competitions",
            "/api/proactive-alerts",
        ):
            self.assertIn("get", paths[path])

        anonymous = await self.client.get("/api/agent-info?agent_id=admin-a")
        profile = await self.client.get(
            "/api/agent-info?agent_id=admin-a", headers=self.admin_headers
        )
        competitions = await self.client.get(
            "/api/competitions?agent_id=admin-a", headers=self.admin_headers
        )
        alerts = await self.client.get(
            "/api/proactive-alerts?agent_id=admin-a", headers=self.admin_headers
        )

        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json()["data"]["agent_id"], "admin-a")
        self.assertEqual(competitions.status_code, 200)
        self.assertEqual(competitions.json()["total_competitions"], 1)
        competition = competitions.json()["competitions"][0]
        self.assertEqual(competition["id"], "competition-a")
        self.assertEqual(competition["urgency_level"], "critical")
        self.assertIn("feasibility_hint", competition)
        self.assertEqual(alerts.status_code, 200)
        self.assertEqual(alerts.json()["alerts"][0]["competition_name"], "Contest a")

    async def test_chat_sessions_are_authenticated_and_user_owned(self) -> None:
        anonymous = await self.client.get("/api/chat-sessions")
        listing = await self.client.get(
            "/api/chat-sessions", headers=self.admin_headers
        )
        detail = await self.client.get(
            "/api/chat-sessions/ws:session-a", headers=self.admin_headers
        )
        foreign = await self.client.get(
            "/api/chat-sessions/ws:session-a", headers=self.reader_headers
        )

        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(
            [item["id"] for item in listing.json()["data"]], ["ws:session-a"]
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(
            [item["role"] for item in detail.json()["data"]["messages"]],
            ["user", "assistant"],
        )
        self.assertEqual(foreign.status_code, 404)

    async def test_briefing_mount_preserves_paths_and_requires_identity(self) -> None:
        paths = self.app.openapi()["paths"]
        self.assertIn("get", paths["/api/briefing/today/summary"])
        self.assertIn("post", paths["/api/briefing/today/regenerate"])
        self.assertIn("get", paths["/api/briefing/messages/{message_id}"])
        self.assertIn("get", paths["/api/briefing/admin/agents"])
        self.assertIn("post", paths["/api/briefing/inbox/ingest"])

        anonymous = await self.client.get("/api/briefing/today/summary?agent_id=admin-a")
        spoofed = await self.client.get(
            "/api/briefing/today/summary?agent_id=reader-b", headers=self.admin_headers
        )
        with patch("api.routers.briefing.get_compliance_warnings", return_value=[]):
            own = await self.client.get(
                "/api/briefing/today/summary?agent_id=admin-a", headers=self.admin_headers
            )
        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(spoofed.status_code, 403)
        self.assertEqual(own.status_code, 200)
        self.assertEqual(own.json()["message_count"], 1)

    async def test_briefing_message_and_admin_scope(self) -> None:
        foreign_message = await self.client.get(
            "/api/briefing/messages/message-b", headers=self.admin_headers
        )
        foreign_read = await self.client.post(
            "/api/briefing/messages/message-b/read", headers=self.admin_headers
        )
        own_message = await self.client.get(
            "/api/briefing/messages/message-a", headers=self.admin_headers
        )
        reader_admin = await self.client.get(
            "/api/briefing/admin/agents?agent_id=reader-b", headers=self.reader_headers
        )
        admin_spoof = await self.client.get(
            "/api/briefing/admin/agents?agent_id=reader-b", headers=self.admin_headers
        )
        admin_own = await self.client.get(
            "/api/briefing/admin/agents?agent_id=admin-a", headers=self.admin_headers
        )
        ingest = await self.client.post(
            "/api/briefing/inbox/ingest", headers=self.admin_headers,
            json={"messages": []},
        )
        async with self.sessions() as session:
            untouched = await session.get(InboxMessage, "message-b")

        self.assertEqual(foreign_message.status_code, 404)
        self.assertEqual(foreign_read.status_code, 404)
        self.assertIsNone(untouched.read_at)
        self.assertEqual(own_message.status_code, 200)
        self.assertEqual(own_message.json()["raw_content"], "private a")
        self.assertEqual(reader_admin.status_code, 403)
        self.assertEqual(admin_spoof.status_code, 403)
        self.assertEqual(admin_own.status_code, 200)
        self.assertEqual(
            [agent["username"] for agent in admin_own.json()["agents"]],
            ["admin-a", "agent-a", "inactive-a"],
        )
        self.assertEqual(ingest.status_code, 403)

    async def test_targets_validate_inputs_and_restrict_writes(self) -> None:
        anonymous = await self.client.get("/api/admin/targets/")
        invalid_page = await self.client.get(
            "/api/admin/targets/?page_size=0", headers=self.admin_headers
        )
        invalid_body = await self.client.post(
            "/api/admin/targets/", headers=self.admin_headers, json={"target_value": 1}
        )
        reader_write = await self.client.post(
            "/api/admin/targets/", headers=self.reader_headers, json={"target_value": 1}
        )

        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(anonymous.json()["detail"]["error"]["code"], "UNAUTHORIZED")
        self.assertEqual(invalid_page.status_code, 422)
        self.assertEqual(invalid_body.status_code, 422)
        self.assertEqual(reader_write.status_code, 403)

    async def test_target_reads_are_tenant_scoped_even_for_shared_agent_id(self) -> None:
        listing = await self.client.get(
            "/api/admin/targets/?agent_id=shared-agent", headers=self.admin_headers
        )
        by_agent = await self.client.get(
            "/api/admin/targets/by-agent/shared-agent", headers=self.admin_headers
        )
        foreign_filter = await self.client.get(
            "/api/admin/targets/?tenant_id=tenant-b", headers=self.admin_headers
        )
        foreign_id = await self.client.get(
            "/api/admin/targets/target-b", headers=self.admin_headers
        )

        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["meta"]["total"], 1)
        self.assertEqual([row["id"] for row in listing.json()["data"]], ["target-a"])
        self.assertEqual(by_agent.status_code, 200)
        self.assertEqual(by_agent.json()["data"]["premium"]["id"], "target-a")
        self.assertEqual(foreign_filter.status_code, 403)
        self.assertEqual(foreign_id.status_code, 403)

    async def test_competition_reads_are_tenant_scoped(self) -> None:
        listing = await self.client.get(
            "/api/admin/competitions/", headers=self.admin_headers
        )
        foreign_filter = await self.client.get(
            "/api/admin/competitions/?tenant_id=tenant-b", headers=self.admin_headers
        )
        foreign_id = await self.client.get(
            "/api/admin/competitions/competition-b", headers=self.admin_headers
        )

        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["meta"]["total"], 1)
        self.assertEqual([row["id"] for row in listing.json()["data"]], ["competition-a"])
        self.assertEqual(foreign_filter.status_code, 403)
        self.assertEqual(foreign_id.status_code, 403)


if __name__ == "__main__":
    unittest.main()
