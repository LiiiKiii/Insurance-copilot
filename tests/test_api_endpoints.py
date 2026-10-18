"""Offline HTTP contracts for the business routes currently mounted by the New Repo.

The Original /api/{performance,competitions,...} routes have not been migrated.
These tests exercise the existing tenant-scoped administrative counterparts.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from admin.db import Base, get_db
from admin.models.competition import Competition
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
                        deadline="2026-12-31",
                    )
                    for suffix in ("a", "b")
                ]
            )
            await session.commit()

        self.admin_headers = {
            "Authorization": f"Bearer {create_access_token({'sub': 'admin-a'})}"
        }
        self.reader_headers = {
            "Authorization": f"Bearer {create_access_token({'sub': 'reader-b'})}"
        }

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.app.dependency_overrides.clear()
        await self.engine.dispose()
        self.directory.cleanup()
        self.audit_patch.stop()
        self.environment.stop()

    async def test_health_is_public_and_reports_lazy_runtime(self) -> None:
        response = await self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "agent_loop": "not_started"})

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
