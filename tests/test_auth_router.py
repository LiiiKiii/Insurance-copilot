"""Offline, database-backed tests for administrative authentication routes."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from jose import jwt
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from admin.db import Base, get_db
from admin.models.tenant import Tenant
from admin.models.user import Role, User
from admin.routers.auth import router as auth_router
from admin.services.auth_service import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
)
from api.server import create_app


TEST_SECRET = "auth-router-test-secret-with-at-least-thirty-two-bytes"


class AuthenticationRouterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.environment = patch.dict(os.environ, {}, clear=False)
        self.environment.start()
        os.environ["ADMIN_SECRET_KEY"] = TEST_SECRET
        self.temporary_directory = tempfile.TemporaryDirectory()
        database_path = Path(self.temporary_directory.name) / "auth-test.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        self.application = create_app()

        async def test_db():
            async with self.sessions() as session:
                yield session

        self.application.dependency_overrides[get_db] = test_db

    async def asyncTearDown(self) -> None:
        self.application.dependency_overrides.clear()
        await self.engine.dispose()
        self.temporary_directory.cleanup()
        self.environment.stop()

    async def _request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        token: str | None = None,
    ) -> tuple[int, dict, dict[str, str]]:
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
        if token is not None:
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
                "query_string": b"",
                "headers": headers,
                "client": ("127.0.0.1", 12345),
                "server": ("testserver", 80),
            },
            receive,
            send,
        )
        start = next(message for message in messages if message["type"] == "http.response.start")
        response_body = b"".join(
            message.get("body", b"")
            for message in messages
            if message["type"] == "http.response.body"
        )
        response_headers = {
            key.decode("latin-1"): value.decode("latin-1")
            for key, value in start.get("headers", [])
        }
        return start["status"], json.loads(response_body), response_headers

    async def _add_user(
        self,
        *,
        username: str = "admin",
        password: str = "correct-password",
        active: bool = True,
        tenant_enabled: bool = True,
        role_names: tuple[str, ...] = ("admin",),
        tier: str = "agent",
        superadmin: bool = False,
        role_tenant_id: str | None = None,
    ) -> tuple[str, str]:
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        async with self.sessions() as session:
            session.add(Tenant(id=tenant_id, slug=f"tenant-{tenant_id}", name="Test", enabled=tenant_enabled))
            if role_tenant_id is not None and role_tenant_id != tenant_id:
                session.add(Tenant(id=role_tenant_id, slug=f"tenant-{role_tenant_id}", name="Other"))
            roles = [
                Role(id=str(uuid.uuid4()), tenant_id=role_tenant_id or tenant_id, name=name)
                for name in role_names
            ]
            user = User(
                id=user_id,
                tenant_id=tenant_id,
                username=username,
                email=f"{user_id}@example.test",
                password_hash=hash_password(password),
                is_active=active,
                is_superadmin=superadmin,
                tier=tier,
                roles=roles,
            )
            session.add(user)
            await session.commit()
        return user_id, tenant_id

    async def _set_user_active(self, user_id: str, active: bool) -> None:
        async with self.sessions() as session:
            user = await session.get(User, user_id)
            assert user is not None
            user.is_active = active
            await session.commit()

    async def _set_tenant_enabled(self, tenant_id: str, enabled: bool) -> None:
        async with self.sessions() as session:
            tenant = await session.get(Tenant, tenant_id)
            assert tenant is not None
            tenant.enabled = enabled
            await session.commit()

    async def _revoke_roles(self, user_id: str) -> None:
        async with self.sessions() as session:
            result = await session.execute(
                select(User).options(selectinload(User.roles)).where(User.id == user_id)
            )
            user = result.scalar_one()
            user.roles.clear()
            await session.commit()

    def _override_with_failing_commit(self, *, rollback_fails: bool) -> dict[str, bool]:
        observed = {"rollback_attempted": False}

        class CommitFailureSession:
            def __init__(self, session: AsyncSession) -> None:
                self._session = session

            async def execute(self, *args, **kwargs):
                return await self._session.execute(*args, **kwargs)

            async def get(self, *args, **kwargs):
                return await self._session.get(*args, **kwargs)

            async def commit(self) -> None:
                raise SQLAlchemyError("commit unavailable")

            async def rollback(self) -> None:
                observed["rollback_attempted"] = True
                if rollback_fails:
                    raise SQLAlchemyError("rollback unavailable")
                await self._session.rollback()

        async def failing_db():
            async with self.sessions() as session:
                yield CommitFailureSession(session)

        self.application.dependency_overrides[get_db] = failing_db
        return observed

    @staticmethod
    def _error_code(body: dict) -> str:
        return body["detail"]["error"]["code"]

    async def test_valid_login_returns_original_compatible_payload_and_updates_last_login(self) -> None:
        user_id, _ = await self._add_user()

        status, body, _ = await self._request(
            "POST", "/api/admin/auth/login", {"username": "admin", "password": "correct-password"}
        )

        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        data = body["data"]
        self.assertEqual(data["token_type"], "bearer")
        self.assertEqual(set(data["user"]), {
            "id", "username", "email", "display_name", "tenant_id", "is_superadmin", "is_admin", "tier", "roles"
        })
        self.assertEqual(data["user"]["id"], user_id)
        self.assertEqual(data["user"]["roles"], ["admin"])
        self.assertEqual(data["access_token"].count("."), 2)
        self.assertEqual(data["refresh_token"].count("."), 2)
        access_claims = decode_token(data["access_token"])
        refresh_claims = decode_token(data["refresh_token"])
        self.assertEqual(access_claims["sub"], user_id)
        self.assertEqual(access_claims["type"], "access")
        self.assertEqual(refresh_claims["sub"], user_id)
        self.assertEqual(refresh_claims["type"], "refresh")
        async with self.sessions() as session:
            self.assertIsNotNone((await session.get(User, user_id)).last_login_at)

    async def test_login_rejects_invalid_unknown_duplicate_and_malformed_credentials(self) -> None:
        await self._add_user(username="known")
        await self._add_user(username="duplicate")
        await self._add_user(username="duplicate")
        malformed_id, _ = await self._add_user(username="malformed")
        async with self.sessions() as session:
            user = await session.get(User, malformed_id)
            assert user is not None
            user.password_hash = "not-a-bcrypt-hash"
            await session.commit()

        for username, password in (("known", "wrong"), ("unknown", "wrong"), ("duplicate", "correct-password"), ("malformed", "correct-password")):
            with self.subTest(username=username):
                status, body, _ = await self._request("POST", "/api/admin/auth/login", {"username": username, "password": password})
                self.assertEqual(status, 401)
                self.assertEqual(self._error_code(body), "INVALID_CREDENTIALS")

    async def test_login_enforces_user_tenant_and_admin_state(self) -> None:
        cases = (
            ("inactive", {"active": False}, "ACCOUNT_DISABLED"),
            ("disabled-tenant", {"tenant_enabled": False}, "TENANT_DISABLED"),
            ("readonly-role", {"role_names": ()}, "NO_ADMIN_ACCESS"),
        )
        for username, kwargs, expected_code in cases:
            with self.subTest(username=username):
                await self._add_user(username=username, **kwargs)
                status, body, _ = await self._request("POST", "/api/admin/auth/login", {"username": username, "password": "correct-password"})
                self.assertEqual(status, 403)
                self.assertEqual(self._error_code(body), expected_code)

    async def test_login_fails_safely_for_database_and_secret_failures(self) -> None:
        await self._add_user()
        os.environ.pop("ADMIN_SECRET_KEY")
        status, body, _ = await self._request("POST", "/api/admin/auth/login", {"username": "admin", "password": "correct-password"})
        self.assertEqual(status, 503)
        self.assertEqual(self._error_code(body), "AUTH_SERVICE_UNAVAILABLE")
        self.assertNotIn(TEST_SECRET, json.dumps(body))

        os.environ["ADMIN_SECRET_KEY"] = TEST_SECRET

        class BrokenSession:
            async def execute(self, *_args, **_kwargs):
                raise SQLAlchemyError("database unavailable")

        async def broken_db():
            yield BrokenSession()

        self.application.dependency_overrides[get_db] = broken_db
        status, body, _ = await self._request("POST", "/api/admin/auth/login", {"username": "admin", "password": "correct-password"})
        self.assertEqual(status, 503)
        self.assertEqual(self._error_code(body), "AUTH_SERVICE_UNAVAILABLE")
        self.assertNotIn("database unavailable", json.dumps(body))

    async def test_login_commit_failure_attempts_rollback_and_returns_safe_error(self) -> None:
        await self._add_user()
        observed = self._override_with_failing_commit(rollback_fails=False)

        status, body, _ = await self._request(
            "POST", "/api/admin/auth/login", {"username": "admin", "password": "correct-password"}
        )

        self.assertEqual(status, 503)
        self.assertEqual(self._error_code(body), "AUTH_SERVICE_UNAVAILABLE")
        self.assertTrue(observed["rollback_attempted"])
        self.assertNotIn("commit unavailable", json.dumps(body))
        self.assertNotIn("access_token", json.dumps(body))

    async def test_login_commit_and_rollback_failure_returns_safe_error(self) -> None:
        await self._add_user()
        observed = self._override_with_failing_commit(rollback_fails=True)

        status, body, _ = await self._request(
            "POST", "/api/admin/auth/login", {"username": "admin", "password": "correct-password"}
        )

        self.assertEqual(status, 503)
        self.assertEqual(self._error_code(body), "AUTH_SERVICE_UNAVAILABLE")
        self.assertTrue(observed["rollback_attempted"])
        self.assertNotIn("commit unavailable", json.dumps(body))
        self.assertNotIn("rollback unavailable", json.dumps(body))

    async def test_me_and_logout_require_live_access_tokens(self) -> None:
        user_id, _ = await self._add_user()
        access = create_access_token({"sub": user_id})

        status, body, _ = await self._request("GET", "/api/admin/auth/me", token=access)
        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["id"], user_id)
        self.assertTrue(body["data"]["is_admin"])

        status, body, headers = await self._request("POST", "/api/admin/auth/logout")
        self.assertEqual(status, 401)
        self.assertEqual(self._error_code(body), "UNAUTHORIZED")
        self.assertEqual(headers["www-authenticate"], "Bearer")

        status, body, _ = await self._request("POST", "/api/admin/auth/logout", token=access)
        self.assertEqual((status, body), (200, {"ok": True, "data": {"message": "Logged out"}}))

    async def test_current_user_rechecks_token_type_signature_expiry_and_live_state(self) -> None:
        user_id, tenant_id = await self._add_user()
        access = create_access_token({"sub": user_id})
        refresh = create_refresh_token({"sub": user_id})
        expired = jwt.encode({"sub": user_id, "type": "access", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)}, TEST_SECRET, algorithm="HS256")
        invalid_signature = jwt.encode({"sub": user_id, "type": "access", "exp": datetime.now(timezone.utc) + timedelta(minutes=1)}, "different-test-secret-with-at-least-thirty-two-bytes", algorithm="HS256")

        for token in (refresh, expired, invalid_signature):
            with self.subTest(token_type=token.split(".")[1][:8]):
                status, body, headers = await self._request("GET", "/api/admin/auth/me", token=token)
                self.assertEqual(status, 401)
                self.assertEqual(self._error_code(body), "INVALID_TOKEN")
                self.assertEqual(headers["www-authenticate"], "Bearer")

        await self._set_user_active(user_id, False)
        status, body, _ = await self._request("GET", "/api/admin/auth/me", token=access)
        self.assertEqual((status, self._error_code(body)), (403, "ACCOUNT_DISABLED"))

        await self._set_user_active(user_id, True)
        await self._set_tenant_enabled(tenant_id, False)
        status, body, _ = await self._request("GET", "/api/admin/auth/me", token=access)
        self.assertEqual((status, self._error_code(body)), (403, "TENANT_DISABLED"))

    async def test_refresh_rechecks_type_expiry_deleted_user_and_role_revocation(self) -> None:
        user_id, _ = await self._add_user()
        refresh = create_refresh_token({"sub": user_id})
        access = create_access_token({"sub": user_id})
        expired_refresh = jwt.encode({"sub": user_id, "type": "refresh", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)}, TEST_SECRET, algorithm="HS256")

        status, body, _ = await self._request("POST", "/api/admin/auth/refresh", {"refresh_token": refresh})
        self.assertEqual(status, 200)
        self.assertEqual(body["data"].keys(), {"access_token", "token_type"})
        self.assertEqual(body["data"]["token_type"], "bearer")
        refresh_access_claims = decode_token(body["data"]["access_token"])
        self.assertEqual(refresh_access_claims["sub"], user_id)
        self.assertEqual(refresh_access_claims["type"], "access")

        for token in (access, expired_refresh):
            status, body, _ = await self._request("POST", "/api/admin/auth/refresh", {"refresh_token": token})
            self.assertEqual((status, self._error_code(body)), (401, "INVALID_TOKEN"))

        await self._revoke_roles(user_id)
        stale_claim_refresh = create_refresh_token({"sub": user_id, "roles": ["admin"]})
        status, body, _ = await self._request("POST", "/api/admin/auth/refresh", {"refresh_token": stale_claim_refresh})
        self.assertEqual((status, self._error_code(body)), (403, "NO_ADMIN_ACCESS"))

        async with self.sessions() as session:
            user = await session.get(User, user_id)
            assert user is not None
            await session.delete(user)
            await session.commit()
        status, body, _ = await self._request("POST", "/api/admin/auth/refresh", {"refresh_token": refresh})
        self.assertEqual((status, self._error_code(body)), (401, "UNAUTHORIZED"))

    async def test_unrelated_tenant_role_and_tier_do_not_grant_admin_access(self) -> None:
        other_tenant_id = str(uuid.uuid4())
        user_id, _ = await self._add_user(
            username="wrong-role-tenant",
            role_names=("admin",),
            role_tenant_id=other_tenant_id,
            tier="director",
        )
        token = create_access_token({"sub": user_id, "roles": ["admin"]})

        status, body, _ = await self._request("POST", "/api/admin/auth/refresh", {"refresh_token": create_refresh_token({"sub": user_id})})
        self.assertEqual((status, self._error_code(body)), (403, "NO_ADMIN_ACCESS"))
        status, body, _ = await self._request("GET", "/api/admin/auth/me", token=token)
        self.assertEqual(status, 200)
        self.assertFalse(body["data"]["is_admin"])
        self.assertEqual(body["data"]["roles"], [])

    async def test_only_auth_router_is_added_and_a3_health_remains_available(self) -> None:
        status, body, _ = await self._request("GET", "/api/health")
        self.assertEqual((status, body), (200, {"status": "ok", "agent_loop": "not_started"}))

        included_routers = [
            getattr(route, "original_router", None)
            for route in self.application.routes
        ]
        self.assertIn(auth_router, included_routers)
        self.assertNotIn(
            "admin.routers.knowledge",
            {router.__module__ for router in included_routers if router is not None},
        )
        paths = [route.path for route in auth_router.routes if hasattr(route, "path")]
        self.assertIn("/api/admin/auth/login", paths)
        self.assertNotIn("/knowledge", paths)


if __name__ == "__main__":
    unittest.main()
