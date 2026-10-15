"""Offline schema, hook, middleware, and reader checks for A4 audit migration."""
from __future__ import annotations

import importlib.util
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request
from sqlalchemy import create_engine, inspect, select, text
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from admin.db import Base, get_db
from admin.hooks import log_ai_audit, log_flow_step, log_token_usage
from admin.middleware.audit_middleware import AdminAuditMiddleware
from admin.models.audit import AiAuditLog, ErrorLog, RequestLog
from admin.models.flow_log import FlowLog
from admin.models.usage import TokenUsageLog
from admin.models.user import Role, User
from admin.dependencies import get_current_user
from admin.services.auth_service import TokenValidationError
from admin.routers.audit import router


class AuditSchemaTests(unittest.TestCase):
    def test_registered_tables_columns_and_indexes(self):
        expected = {
            "request_logs": {"id": ("VARCHAR(36)", False), "tenant_id": ("VARCHAR(36)", True), "user_id": ("VARCHAR(36)", True), "endpoint": ("VARCHAR(500)", False), "method": ("VARCHAR(10)", False), "status_code": ("INTEGER", False), "latency_ms": ("INTEGER", False), "ip_address": ("VARCHAR(50)", False), "user_agent": ("VARCHAR(500)", False), "created_at": ("DATETIME", False)},
            "ai_audit_logs": {"id": ("VARCHAR(36)", False), "tenant_id": ("VARCHAR(36)", True), "user_id": ("VARCHAR(36)", True), "session_id": ("VARCHAR(100)", False), "agent_id": ("VARCHAR(100)", False), "user_query": ("TEXT", False), "ai_response": ("TEXT", False), "tools_called": ("VARCHAR(2000)", False), "model_id": ("VARCHAR(200)", False), "prompt_tokens": ("INTEGER", False), "completion_tokens": ("INTEGER", False), "has_compliance_issue": ("BOOLEAN", False), "compliance_notes": ("VARCHAR(1000)", True), "created_at": ("DATETIME", False)},
            "error_logs": {"id": ("VARCHAR(36)", False), "tenant_id": ("VARCHAR(36)", True), "level": ("VARCHAR(10)", False), "message": ("TEXT", False), "stack_trace": ("TEXT", True), "context": ("VARCHAR(2000)", False), "created_at": ("DATETIME", False)},
            "token_usage_logs": {"id": ("VARCHAR(36)", False), "tenant_id": ("VARCHAR(36)", True), "user_id": ("VARCHAR(36)", True), "session_id": ("VARCHAR(100)", True), "model_id": ("VARCHAR(200)", False), "model_display_name": ("VARCHAR(200)", False), "model_category": ("VARCHAR(20)", False), "prompt_tokens": ("INTEGER", False), "completion_tokens": ("INTEGER", False), "total_tokens": ("INTEGER", False), "cost_usd": ("FLOAT", False), "latency_ms": ("INTEGER", False), "created_at": ("DATETIME", False)},
            "flow_logs": {"id": ("VARCHAR(36)", False), "session_id": ("VARCHAR(100)", False), "agent_id": ("VARCHAR(100)", False), "step_index": ("INTEGER", False), "step_type": ("VARCHAR(20)", False), "content": ("TEXT", False), "metadata_json": ("TEXT", True), "latency_ms": ("INTEGER", False), "created_at": ("DATETIME", False)},
        }
        with tempfile.TemporaryDirectory() as folder:
            engine = create_engine(f"sqlite:///{Path(folder) / 'schema.db'}")
            Base.metadata.create_all(engine)
            inspector = inspect(engine)
            for model in (RequestLog, AiAuditLog, ErrorLog, TokenUsageLog, FlowLog):
                self.assertTrue(inspector.has_table(model.__tablename__))
                columns = {column["name"] for column in inspector.get_columns(model.__tablename__)}
                self.assertEqual(columns, set(model.__table__.columns.keys()))
                actual = {column["name"]: (str(column["type"]).upper(), column["nullable"]) for column in inspector.get_columns(model.__tablename__)}
                self.assertEqual(actual, expected[model.__tablename__])
            for name, column in (
                ("request_logs", "user_id"), ("ai_audit_logs", "user_id"),
                ("token_usage_logs", "user_id"), ("flow_logs", "session_id"),
                ("flow_logs", "agent_id"),
            ):
                self.assertIn([column], [index["column_names"] for index in inspector.get_indexes(name)])
            self.assertEqual(inspector.get_columns("ai_audit_logs")[7]["name"], "tools_called")
            engine.dispose()

    def test_forward_migration_handles_precreated_tables(self):
        path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0003_audit_logs.py"
        spec = importlib.util.spec_from_file_location("audit_migration_0003", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            Base.metadata.create_all(connection)
            with patch.object(module.op, "get_bind", return_value=connection):
                module.upgrade()
        self.assertTrue(inspect(engine).has_table("request_logs"))
        engine.dispose()

    def test_forward_migration_creates_missing_tables(self):
        path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0003_audit_logs.py"
        spec = importlib.util.spec_from_file_location("audit_migration_0003_new", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            with patch.object(module.op, "get_bind", return_value=connection):
                module.upgrade()
        self.assertTrue(all(inspect(engine).has_table(name) for name in module._TABLES))
        engine.dispose()

    def test_forward_migration_adds_legacy_user_id(self):
        path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0003_audit_logs.py"
        spec = importlib.util.spec_from_file_location("audit_migration_0003_legacy", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE request_logs (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36), endpoint VARCHAR(500) NOT NULL, method VARCHAR(10) NOT NULL, status_code INTEGER NOT NULL, latency_ms INTEGER, ip_address VARCHAR(50), user_agent VARCHAR(500), created_at DATETIME)"))
            connection.execute(text("INSERT INTO request_logs (id, endpoint, method, status_code) VALUES ('old', '/api/old', 'GET', 200)"))
            operations = Operations(MigrationContext.configure(connection))
            with patch.object(module, "op", operations):
                module.upgrade()
            self.assertEqual(connection.execute(text("SELECT id FROM request_logs")).scalar_one(), "old")
        self.assertIn("user_id", {column["name"] for column in inspect(engine).get_columns("request_logs")})
        engine.dispose()


class AuditHooksTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{Path(self.folder.name, 'audit.db').as_posix()}")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.factory_patch = patch("admin.hooks.AsyncSessionFactory", self.sessions)
        self.factory_patch.start()

    async def asyncTearDown(self):
        self.factory_patch.stop()
        await self.engine.dispose()
        self.folder.cleanup()

    async def test_hooks_persist_truncate_and_redact(self):
        await log_ai_audit("s", "a", "x" * 2100, "Bearer secret " + "y" * 5100, tools_called='["tool"]')
        await log_flow_step("s", "a", 0, "response", "password=secret " + "z" * 5100, '{"token":"secret"}')
        await log_token_usage("model", None, 2, 3, 5, cost_usd=0.5)
        async with self.sessions() as db:
            ai = (await db.scalars(select(AiAuditLog))).one()
            flow = (await db.scalars(select(FlowLog))).one()
            usage = (await db.scalars(select(TokenUsageLog))).one()
        self.assertEqual(len(ai.user_query), 2000)
        self.assertLessEqual(len(ai.ai_response), 5000)
        self.assertNotIn("secret", ai.ai_response)
        self.assertEqual(ai.tools_called, '["tool"]')
        self.assertNotIn("secret", flow.content + flow.metadata_json)
        self.assertEqual((usage.total_tokens, usage.cost_usd), (5, 0.5))

    async def test_failure_is_suppressed_and_diagnostic_is_sanitized(self):
        with patch("admin.hooks.AsyncSessionFactory", side_effect=RuntimeError("password=secret")):
            with self.assertLogs("admin.hooks", logging.WARNING) as captured:
                await log_ai_audit("s", "a", "query", "response")
        self.assertNotIn("secret", " ".join(captured.output))


class AuditMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_status_identity_and_untracked_path(self):
        calls = []

        async def endpoint(scope, receive, send):
            scope.setdefault("state", {})["audit_principal"] = ("user", "tenant")
            await send({"type": "http.response.start", "status": 201, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = AdminAuditMiddleware(endpoint)

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            calls.append(message)

        with patch("admin.middleware.audit_middleware._write_log_sync") as writer:
            await middleware({"type": "http", "path": "/api/test", "method": "POST", "headers": [], "client": ("127.0.0.1", 1)}, receive, send)
            self.assertEqual(writer.call_args.args[1:3], ("tenant", "user"))
            self.assertEqual(writer.call_args.args[5], 201)
            await middleware({"type": "http", "path": "/health", "method": "GET", "headers": []}, receive, send)
            self.assertEqual(writer.call_count, 1)
        self.assertEqual(calls[0]["status"], 201)

    async def test_exception_is_audited_as_failure(self):
        async def endpoint(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            raise RuntimeError("failed after response start")

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            pass

        with patch("admin.middleware.audit_middleware._write_log_sync") as writer:
            with self.assertRaises(RuntimeError):
                await AdminAuditMiddleware(endpoint)(
                    {"type": "http", "path": "/api/test", "method": "GET", "headers": []}, receive, send,
                )
            self.assertEqual(writer.call_args.args[1:3], (None, None))
            self.assertEqual(writer.call_args.args[5], 500)

    async def test_principal_comes_from_verified_live_user(self):
        user = User(id="live-user", tenant_id="live-tenant", is_active=True)
        request = Request({"type": "http", "state": {}})
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="signed-token")
        with patch("admin.dependencies.decode_token", return_value={"type": "access", "sub": "live-user", "tenant_id": "stale-tenant"}), patch("admin.dependencies._load_current_user", return_value=user):
            result = await get_current_user(request, credentials, None)
        self.assertIs(result, user)
        self.assertEqual(request.state.audit_principal, ("live-user", "live-tenant"))

        invalid_request = Request({"type": "http", "state": {}})
        with patch("admin.dependencies.decode_token", side_effect=TokenValidationError("invalid")):
            with self.assertRaises(HTTPException):
                await get_current_user(invalid_request, credentials, None)
        self.assertFalse(hasattr(invalid_request.state, "audit_principal"))

    async def test_streaming_response_survives_audit_failure(self):
        sent = []

        async def endpoint(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"first", "more_body": True})
            await send({"type": "http.response.body", "body": b"second", "more_body": False})

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        with patch("admin.middleware.audit_middleware._write_log_sync", side_effect=RuntimeError("password=secret")):
            with self.assertLogs("admin.middleware.audit_middleware", logging.WARNING) as captured:
                await AdminAuditMiddleware(endpoint)(
                    {"type": "http", "path": "/api/stream", "method": "GET", "headers": []}, receive, send,
                )
        self.assertEqual([item.get("body") for item in sent[1:]], [b"first", b"second"])
        self.assertNotIn("secret", " ".join(captured.output))


class AuditReaderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{Path(self.folder.name, 'readers.db').as_posix()}")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.app = FastAPI()
        self.app.include_router(router)

        async def test_db():
            async with self.sessions() as db:
                yield db

        self.app.dependency_overrides[get_db] = test_db

    async def asyncTearDown(self):
        self.app.dependency_overrides.clear()
        await self.engine.dispose()
        self.folder.cleanup()

    async def test_anonymous_is_denied(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test") as client:
            response = await client.get("/api/admin/logs/requests")
        self.assertEqual(response.status_code, 401)

    async def test_tenant_and_role_boundaries(self):
        async with self.sessions() as db:
            db.add_all([
                RequestLog(id="r1", tenant_id="ta", user_id="ua", endpoint="/api/a", method="GET", status_code=200),
                RequestLog(id="r2", tenant_id="ta", user_id="other", endpoint="/api/a", method="GET", status_code=201),
                RequestLog(id="r3", tenant_id="tb", user_id="ub", endpoint="/api/b", method="GET", status_code=202),
                RequestLog(id="r4", tenant_id=None, user_id=None, endpoint="/api/null", method="GET", status_code=203),
                AiAuditLog(id="a1", tenant_id="ta", user_id="ua", session_id="s", agent_id="spoof", user_query="x" * 300, ai_response="y" * 600),
                AiAuditLog(id="a2", tenant_id="tb", user_id="ub", session_id="s", agent_id="spoof", user_query="private", ai_response="private"),
                ErrorLog(id="e1", tenant_id="ta", message="failure", stack_trace="secret stack", context="secret context"),
                ErrorLog(id="e2", tenant_id="tb", message="other"),
            ])
            await db.commit()

        def user(user_id, tenant, role="admin", superadmin=False):
            return User(id=user_id, tenant_id=tenant, is_active=True, is_superadmin=superadmin,
                        roles=[Role(tenant_id=tenant, name=role)])

        current = user("ua", "ta")
        self.app.dependency_overrides[get_current_user] = lambda: current
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test") as client:
            requests = (await client.get("/api/admin/logs/requests?tenant_id=tb")).json()
            self.assertEqual(requests["meta"]["total"], 0)
            requests = (await client.get("/api/admin/logs/requests?page_size=1")).json()
            self.assertEqual(requests["meta"]["total"], 2)
            self.assertEqual(len(requests["data"]), 1)
            self.assertEqual((await client.get("/api/admin/logs/requests?page_size=201")).status_code, 422)
            ai = (await client.get("/api/admin/logs/ai-audit?agent_id=spoof")).json()
            self.assertEqual(ai["meta"]["total"], 1)
            self.assertEqual(len(ai["data"][0]["user_query"]), 200)
            self.assertEqual((await client.get("/api/admin/logs/ai-audit?page_size=101")).status_code, 422)
            errors = (await client.get("/api/admin/logs/errors")).json()
            self.assertEqual(errors["meta"]["total"], 1)
            self.assertIn("stack_trace", errors["data"][0])

            current = user("ua", "ta", "readonly")
            requests = (await client.get("/api/admin/logs/requests")).json()
            self.assertEqual(requests["meta"]["total"], 1)
            errors = (await client.get("/api/admin/logs/errors")).json()
            self.assertNotIn("stack_trace", errors["data"][0])
            self.assertNotIn("context", errors["data"][0])

            current = user("root", "ta", superadmin=True)
            requests = (await client.get("/api/admin/logs/requests")).json()
            self.assertEqual(requests["meta"]["total"], 4)
        self.app.dependency_overrides.pop(get_current_user)
