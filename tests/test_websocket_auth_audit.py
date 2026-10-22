"""Offline WebSocket JWT, identity, and audit integration checks."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from admin.db import Base
from admin.models.audit import AiAuditLog
from admin.models.chat_session import ChatMessage, ChatSession
from admin.models.flow_log import FlowLog
from admin.models.tenant import Tenant
from admin.models.usage import TokenUsageLog
from admin.models.user import User
from admin.services.auth_service import create_access_token, create_refresh_token
from admin.services.auth_service import TokenValidationError
from api.server import create_app


class Socket:
    def __init__(self, app, headers=None):
        self.app = app
        self.headers = headers or []
        self.incoming = asyncio.Queue()
        self.outgoing = asyncio.Queue()
        self.task = None

    async def start(self):
        async def receive():
            return await self.incoming.get()

        async def send(event):
            await self.outgoing.put(event)

        self.task = asyncio.create_task(self.app({
            "type": "websocket", "asgi": {"version": "3.0"}, "scheme": "ws",
            "path": "/ws/chat", "raw_path": b"/ws/chat", "query_string": b"",
            "headers": self.headers, "client": ("127.0.0.1", 1),
            "server": ("testserver", 80), "subprotocols": [],
        }, receive, send))
        await self.incoming.put({"type": "websocket.connect"})
        return await asyncio.wait_for(self.outgoing.get(), 1)

    async def send(self, payload):
        await self.incoming.put({"type": "websocket.receive", "text": json.dumps(payload)})

    async def next(self):
        event = await asyncio.wait_for(self.outgoing.get(), 2)
        if event["type"] == "websocket.send":
            return json.loads(event["text"])
        return event

    async def stop(self):
        if self.task is not None and not self.task.done():
            await self.incoming.put({"type": "websocket.disconnect", "code": 1000})
        if self.task is not None:
            if self.task.cancelled():
                return
            await asyncio.wait_for(self.task, 2)


class WebSocketAuthAuditTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.environment = patch.dict(os.environ, {"ADMIN_SECRET_KEY": "websocket-auth-test-secret-with-32-bytes"})
        self.environment.start()
        self.folder = tempfile.TemporaryDirectory()
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{Path(self.folder.name, 'ws.db').as_posix()}")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with self.sessions() as db:
            db.add_all([
                Tenant(id="tenant-a", slug="tenant-a", name="Tenant A"),
                Tenant(id="tenant-b", slug="tenant-b", name="Tenant B"),
                User(id="user-a", tenant_id="tenant-a", username="alice", email="alice@example.test", password_hash="unused"),
                User(id="user-b", tenant_id="tenant-b", username="bob", email="bob@example.test", password_hash="unused"),
            ])
            await db.commit()
        self.token_a = create_access_token({"sub": "user-a"})
        self.token_b = create_access_token({"sub": "user-b"})
        self.runtime = SimpleNamespace(is_running=True, agent_loop=SimpleNamespace(
            model="verified-model", process_direct=AsyncMock(return_value=SimpleNamespace(content="Answer Bearer response-secret")),
        ))
        self.app = create_app(runtime=self.runtime)
        self.ws_factory = patch("api.ws.AsyncSessionFactory", self.sessions)
        self.hook_factory = patch("admin.hooks.AsyncSessionFactory", self.sessions)
        self.ws_factory.start()
        self.hook_factory.start()
        self.sockets = []

    async def asyncTearDown(self):
        for socket in self.sockets:
            await socket.stop()
        self.hook_factory.stop()
        self.ws_factory.stop()
        await self.engine.dispose()
        self.folder.cleanup()
        self.environment.stop()

    async def socket(self, headers=None):
        socket = Socket(self.app, headers)
        self.sockets.append(socket)
        return socket

    async def authenticate(self, token):
        socket = await self.socket()
        self.assertEqual((await socket.start())["type"], "websocket.accept")
        await socket.send({"type": "auth", "token": token})
        return socket, await socket.next()

    async def test_authentication_failures_and_no_agent_call(self):
        for frame in (
            {"message": "unauthenticated", "agent_id": "alice"},
            {"type": "auth", "token": "invalid"},
            {"type": "auth", "token": create_refresh_token({"sub": "user-a"})},
            {"type": "auth", "token": jwt.encode({"sub": "user-a", "type": "access", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)}, os.environ["ADMIN_SECRET_KEY"], algorithm="HS256")},
            {"type": "auth", "token": "x" * 9000},
        ):
            socket = await self.socket()
            self.assertEqual((await socket.start())["type"], "websocket.accept")
            await socket.send(frame)
            self.assertEqual((await socket.next())["type"], "websocket.close")
        self.runtime.agent_loop.process_direct.assert_not_awaited()

    async def test_disabled_deleted_and_expired_during_connection(self):
        socket, auth = await self.authenticate(self.token_a)
        self.assertEqual(auth, {"type": "auth_ok"})
        async with self.sessions() as db:
            user = await db.get(User, "user-a")
            user.is_active = False
            await db.commit()
        await socket.send({"message": "hello", "agent_id": "alice"})
        self.assertEqual((await socket.next())["type"], "websocket.close")
        self.runtime.agent_loop.process_direct.assert_not_awaited()

        denied, event = await self.authenticate(self.token_a)
        self.assertEqual(event["type"], "websocket.close")
        async with self.sessions() as db:
            user = await db.get(User, "user-a")
            await db.delete(user)
            await db.commit()
        denied, event = await self.authenticate(self.token_a)
        self.assertEqual(event["type"], "websocket.close")

    async def test_existing_token_rejected_after_username_becomes_ambiguous(self):
        async with self.sessions() as db:
            db.add(User(id="duplicate", tenant_id="tenant-b", username="alice", email="duplicate@example.test", password_hash="unused"))
            await db.commit()
        socket, event = await self.authenticate(self.token_a)
        self.assertEqual(event["type"], "websocket.close")
        self.runtime.agent_loop.process_direct.assert_not_awaited()

    async def test_disabled_tenant_is_rejected(self):
        async with self.sessions() as db:
            tenant = await db.get(Tenant, "tenant-a")
            tenant.enabled = False
            await db.commit()
        socket, event = await self.authenticate(self.token_a)
        self.assertEqual(event["type"], "websocket.close")
        self.runtime.agent_loop.process_direct.assert_not_awaited()

    async def test_identity_session_and_audit_persistence(self):
        socket, auth = await self.authenticate(self.token_a)
        self.assertEqual(auth, {"type": "auth_ok"})
        await socket.send({"message": "steal", "agent_id": "bob", "session_id": "ws:target"})
        self.assertEqual((await socket.next())["type"], "error")
        self.runtime.agent_loop.process_direct.assert_not_awaited()

        await socket.send({"message": "Bearer input-secret", "agent_id": "alice", "session_id": "ws:target", "turn_id": "turn:1"})
        response = await socket.next()
        self.assertEqual(response["type"], "response")
        self.assertNotEqual(response["session_id"], "ws:target")
        self.assertEqual(response["turn_id"], "turn:1")
        self.assertEqual(self.runtime.agent_loop.process_direct.await_args.kwargs["session_key"], response["session_id"])
        await socket.send({"message": "second", "agent_id": "alice", "session_id": response["session_id"]})
        second = await socket.next()
        self.assertEqual(second["session_id"], response["session_id"])
        async with self.sessions() as db:
            ai = (await db.scalars(select(AiAuditLog).order_by(AiAuditLog.created_at))).all()
            flows = (await db.scalars(select(FlowLog))).all()
            usage = (await db.scalars(select(TokenUsageLog))).all()
            chat_session = await db.get(ChatSession, response["session_id"])
            chat_messages = (
                await db.scalars(
                    select(ChatMessage)
                    .where(ChatMessage.session_id == response["session_id"])
                    .order_by(ChatMessage.created_at, ChatMessage.id)
                )
            ).all()
        self.assertEqual(len(ai), 2)
        self.assertEqual(len(flows), 6)
        self.assertEqual(len(usage), 0)
        self.assertEqual((ai[0].user_id, ai[0].tenant_id, ai[0].session_id), ("user-a", "tenant-a", response["session_id"]))
        self.assertEqual(ai[0].model_id, "verified-model")
        self.assertEqual(ai[0].tools_called, "[]")
        self.assertNotIn("input-secret", ai[0].user_query)
        self.assertNotIn("response-secret", ai[0].ai_response)
        self.assertEqual([item.step_type for item in flows[:3]], ["user_input", "llm_call", "response"])
        self.assertEqual(chat_session.user_id, "user-a")
        self.assertEqual(chat_session.message_count, 4)
        self.assertEqual(
            [message.role for message in chat_messages],
            ["user", "assistant", "user", "assistant"],
        )

        other, _ = await self.authenticate(self.token_b)
        await other.send({"message": "other tenant", "agent_id": "bob", "session_id": "ws:target"})
        other_response = await other.next()
        self.assertNotEqual(other_response["session_id"], response["session_id"])
        async with self.sessions() as db:
            other_ai = (await db.scalars(select(AiAuditLog).where(AiAuditLog.user_id == "user-b"))).one()
        self.assertEqual((other_ai.tenant_id, other_ai.session_id), ("tenant-b", other_response["session_id"]))

    async def test_audit_failure_does_not_break_response(self):
        socket, _ = await self.authenticate(self.token_a)
        with patch("api.ws.log_flow_step", side_effect=RuntimeError("secret")), patch("api.ws.log_ai_audit", side_effect=RuntimeError("secret")):
            await socket.send({"message": "hello", "agent_id": "alice"})
            response = await socket.next()
        self.assertEqual(response["type"], "response")

    async def test_origin_and_auth_timeout(self):
        unsafe = await self.socket([(b"host", b"testserver"), (b"origin", b"http://evil.example")])
        self.assertEqual((await unsafe.start())["type"], "websocket.close")
        with patch.dict(os.environ, {"WS_ALLOWED_ORIGINS": "https://frontend.example"}):
            allowed = await self.socket([(b"host", b"backend.internal"), (b"origin", b"https://frontend.example")])
            self.assertEqual((await allowed.start())["type"], "websocket.accept")
            await allowed.send({"type": "auth", "token": self.token_a})
            self.assertEqual(await allowed.next(), {"type": "auth_ok"})
        with patch("api.ws._AUTH_TIMEOUT_SECONDS", 0.01):
            missing = await self.socket()
            self.assertEqual((await missing.start())["type"], "websocket.accept")
            self.assertEqual((await missing.next())["type"], "websocket.close")
        self.runtime.agent_loop.process_direct.assert_not_awaited()

    async def test_per_turn_token_revalidation_and_cancellation(self):
        user = SimpleNamespace(id="user-a", tenant_id="tenant-a", username="alice")
        with patch("api.ws.authenticate_access_token", new_callable=AsyncMock) as authenticate:
            authenticate.side_effect = [user, TokenValidationError("expired")]
            socket, auth = await self.authenticate(self.token_a)
            self.assertEqual(auth, {"type": "auth_ok"})
            await socket.send({"message": "after expiry", "agent_id": "alice"})
            self.assertEqual((await socket.next())["type"], "websocket.close")
            self.runtime.agent_loop.process_direct.assert_not_awaited()

        waiting, _ = await self.authenticate(self.token_b)
        waiting.task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiting.task
