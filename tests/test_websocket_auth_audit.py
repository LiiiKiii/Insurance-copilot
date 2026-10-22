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
from admin.models.chat import ChatMessage, ChatSession
from admin.models.flow_log import FlowLog
from admin.models.tenant import Tenant
from admin.models.usage import TokenUsageLog
from admin.models.user import User
from admin.services.auth_service import create_access_token, create_refresh_token
from admin.services.auth_service import TokenValidationError
from api.server import create_app
from nanobot.agent.coursework_demo import CourseworkCandidateSource
from nanobot.agent.loop import AgentLoop
from nanobot.agent.tools.insurance.reasoning_layer.composition import build_reasoning_registry
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMResponse, ToolCallRequest


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
                Tenant(id="demo-tenant", slug="coursework-demo", name="Coursework Demo"),
                User(id="user-a", tenant_id="tenant-a", username="alice", email="alice@example.test", password_hash="unused"),
                User(id="user-b", tenant_id="tenant-b", username="bob", email="bob@example.test", password_hash="unused"),
                User(id="demo-user", tenant_id="demo-tenant", username="AGT00690", email="demo@example.test", password_hash="unused"),
            ])
            await db.commit()
        self.token_a = create_access_token({"sub": "user-a"})
        self.token_b = create_access_token({"sub": "user-b"})
        self.token_demo = create_access_token({"sub": "demo-user"})
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

    async def test_model_supplied_candidates_fail_closed_and_are_audited(self):
        fixture_path = Path(__file__).resolve().parents[1] / "data" / "evaluation" / "prioritization_synthetic.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        candidate = {"candidate_id": "POL-P", "permission_allowed": False,
                     "expected_contribution": 100000, "urgency": 1, "actionability": 1}
        arguments = {
            "agent_id": "alice", "objective": fixture["objective"],
            "candidates": [*fixture["candidates"], candidate],
            "constraints": fixture["constraints"],
        }
        provider = SimpleNamespace(
            get_default_model=lambda: "scripted-model",
            chat_with_retry=AsyncMock(side_effect=[
                LLMResponse(content=None, tool_calls=[ToolCallRequest(
                    id="priority-call-1", name="prioritize_followups", arguments=arguments,
                )], finish_reason="tool_calls"),
            ]),
        )
        self.runtime.agent_loop = AgentLoop(
            MessageBus(), provider, Path(self.folder.name),
            tool_registry=build_reasoning_registry(Path(self.folder.name)),
        )
        socket, auth = await self.authenticate(self.token_a)
        self.assertEqual(auth, {"type": "auth_ok"})
        await socket.send({"message": "Which follow-ups should I prioritize?",
                           "agent_id": "alice", "turn_id": "turn:evaluation"})
        response = await socket.next()

        self.assertEqual(response["type"], "response")
        self.assertEqual(response["content"], "Verified follow-up candidates are unavailable.")
        self.assertEqual(response["turn_id"], "turn:evaluation")
        offered = provider.chat_with_retry.await_args_list[0].kwargs["tools"]
        self.assertNotIn("prioritize_followups", [row["function"]["name"] for row in offered])
        self.assertEqual(provider.chat_with_retry.await_count, 1)
        self.assertNotIn("POL-P", json.dumps(response))
        self.assertNotIn("POL-X", json.dumps(response))
        self.assertNotIn("result", response)

        async with self.sessions() as db:
            ai = (await db.scalars(select(AiAuditLog))).one()
            flows = (await db.scalars(select(FlowLog).order_by(FlowLog.step_index))).all()
            assistant_message = (await db.scalars(select(ChatMessage).where(ChatMessage.role == "assistant"))).one()
        self.assertEqual((ai.tenant_id, ai.user_id, ai.session_id),
                         ("tenant-a", "user-a", response["session_id"]))
        self.assertEqual(json.loads(ai.tools_called), ["prioritize_followups"])
        self.assertEqual([row.step_type for row in flows],
                         ["user_input", "llm_call", "tool_call", "response"])
        self.assertEqual(flows[2].content, "prioritize_followups")
        self.assertEqual(json.loads(flows[2].metadata_json), {
            "tool_call_id": "priority-call-1", "status": "candidate_source_unavailable",
            "turn_id": "turn:evaluation",
        })
        self.assertEqual(assistant_message.metadata_json["tool_events"][0]["status"],
                         "candidate_source_unavailable")
        self.assertNotIn("POL-P", ai.ai_response)
        self.assertNotIn("POL-X", ai.ai_response)
        self.assertNotIn("POL-P", json.dumps(assistant_message.metadata_json))
        self.assertNotIn("POL-X", json.dumps(assistant_message.metadata_json))
        self.assertTrue(all("POL-P" not in (row.content or "") for row in flows))
        self.assertTrue(all("POL-X" not in (row.content or "") for row in flows))

    async def test_other_tenant_cannot_use_model_supplied_candidate_id(self):
        provider = SimpleNamespace(
            get_default_model=lambda: "scripted-model",
            chat_with_retry=AsyncMock(return_value=LLMResponse(
                content=None,
                tool_calls=[ToolCallRequest(
                    id="tenant-call", name="prioritize_followups",
                    arguments={
                        "agent_id": "bob", "objective": {"open_gap": 100},
                        "candidates": [{"candidate_id": "tenant-a-private-policy"}],
                    },
                )],
                finish_reason="tool_calls",
            )),
        )
        self.runtime.agent_loop = AgentLoop(
            MessageBus(), provider, Path(self.folder.name),
            tool_registry=build_reasoning_registry(Path(self.folder.name)),
        )
        with patch.dict(os.environ, {"M1_COURSEWORK_DEMO_TENANT_ID": "demo-tenant"}):
            socket, _ = await self.authenticate(self.token_b)
            await socket.send({"message": "Prioritize", "agent_id": "bob"})
            response = await socket.next()

        self.assertEqual(response["content"], "Verified follow-up candidates are unavailable.")
        self.assertNotIn("tenant-a-private-policy", json.dumps(response))
        self.assertEqual(provider.chat_with_retry.await_count, 1)
        async with self.sessions() as db:
            audit = (await db.scalars(select(AiAuditLog))).one()
        self.assertEqual((audit.user_id, audit.tenant_id), ("user-b", "tenant-b"))
        self.assertNotIn("tenant-a-private-policy", audit.ai_response)

    async def test_demo_jwt_cannot_choose_another_scenario_agent(self):
        with patch.dict(os.environ, {"M1_COURSEWORK_DEMO_TENANT_ID": "demo-tenant"}):
            socket, _ = await self.authenticate(self.token_demo)
            await socket.send({
                "message": "Prioritize", "agent_id": "AGT00770",
                "scenario_id": "SCN-AGT00770",
            })
            response = await socket.next()
        self.assertEqual(response["type"], "error")
        self.assertEqual(response["content"], "agent_id is not authorized.")
        self.runtime.agent_loop.process_direct.assert_not_awaited()

    async def test_configured_non_demo_tenant_slug_stays_fail_closed(self):
        provider = SimpleNamespace(
            get_default_model=lambda: "scripted-model",
            chat_with_retry=AsyncMock(return_value=LLMResponse(
                content=None, tool_calls=[ToolCallRequest(
                    id="slug-call", name="prioritize_followups", arguments={},
                )], finish_reason="tool_calls",
            )),
        )
        self.runtime.agent_loop = AgentLoop(
            MessageBus(), provider, Path(self.folder.name),
            tool_registry=build_reasoning_registry(Path(self.folder.name)),
        )
        with patch.dict(os.environ, {"M1_COURSEWORK_DEMO_TENANT_ID": "tenant-a"}):
            socket, _ = await self.authenticate(self.token_a)
            await socket.send({"message": "Prioritize", "agent_id": "alice"})
            response = await socket.next()
        self.assertEqual(response["content"], "Verified follow-up candidates are unavailable.")
        self.assertNotIn("result", response)
        offered = provider.chat_with_retry.await_args_list[0].kwargs["tools"]
        self.assertNotIn("prioritize_followups", [row["function"]["name"] for row in offered])

    async def test_authenticated_coursework_recommendation_returns_card_and_audit(self):
        provider = SimpleNamespace(
            get_default_model=lambda: "scripted-model",
            chat_with_retry=AsyncMock(side_effect=[
                LLMResponse(content=None, tool_calls=[ToolCallRequest(
                    id="demo-call-1", name="prioritize_followups", arguments={},
                )], finish_reason="tool_calls"),
                LLMResponse(content="Contact the customer about the missing documents first."),
            ]),
        )
        self.runtime.agent_loop = AgentLoop(
            MessageBus(), provider, Path(self.folder.name),
            tool_registry=build_reasoning_registry(Path(self.folder.name)),
        )
        with patch.dict(os.environ, {"M1_COURSEWORK_DEMO_TENANT_ID": "demo-tenant"}):
            socket, auth = await self.authenticate(self.token_demo)
            self.assertEqual(auth, {"type": "auth_ok"})
            await socket.send({
                "message": "What should I follow up first?", "agent_id": "AGT00690",
                "turn_id": "turn:demo",
            })
            response = await socket.next()

        self.assertEqual(response["type"], "response")
        self.assertEqual(response["content"], "Contact the customer about the missing documents first.")
        self.assertEqual(response["turn_id"], "turn:demo")
        card = response["result"]
        self.assertEqual((card["kind"], card["source"], card["scenario_id"], card["tool_call_id"]),
                         ("action_plan", "m2-coursework-candidates-v3", "SCN-AGT00690", "demo-call-1"))
        self.assertEqual(card["as_of_date"], "2026-05-31")
        self.assertEqual([row["rank"] for row in card["actions"]], [1, 2, 3, 4, 5])
        self.assertEqual(card["actions"][0]["candidate_id"], "POL-00690-001")
        self.assertIn("action_signal", card["actions"][0]["evidence"])
        self.assertIn("expected_contribution", card["actions"][0]["score_components"])
        offered = provider.chat_with_retry.await_args_list[0].kwargs["tools"]
        facade = next(row for row in offered if row["function"]["name"] == "prioritize_followups")
        self.assertEqual(facade["function"]["parameters"]["properties"], {})
        self.assertNotIn("candidates", json.dumps(offered))
        history = provider.chat_with_retry.await_args_list[1].kwargs["messages"]
        assistant = next(row for row in history if row.get("tool_calls"))
        tool_result = next(row for row in history if row.get("role") == "tool")
        self.assertEqual(assistant["tool_calls"][0]["function"]["arguments"], "{}")
        self.assertEqual(tool_result["tool_call_id"], "demo-call-1")
        ranked = json.loads(tool_result["content"])
        self.assertEqual(ranked["source"], "m2-coursework-candidates-v3")
        self.assertEqual(ranked["excluded_candidates"], [])
        self.assertEqual(ranked["candidate_count"], 6)
        for excluded in ("POL-00690-003", "POL-00690-004", "CLI-00690-013", "CLI-00690-015"):
            self.assertNotIn(excluded, tool_result["content"])
            self.assertNotIn(excluded, json.dumps(card))

        async with self.sessions() as db:
            audit = (await db.scalars(select(AiAuditLog))).one()
            flows = (await db.scalars(select(FlowLog).order_by(FlowLog.step_index))).all()
            assistant_message = (await db.scalars(select(ChatMessage).where(ChatMessage.role == "assistant"))).one()
        self.assertEqual((audit.user_id, audit.tenant_id), ("demo-user", "demo-tenant"))
        self.assertEqual(json.loads(audit.tools_called), ["prioritize_followups"])
        self.assertEqual([row.step_type for row in flows],
                         ["user_input", "llm_call", "tool_call", "response"])
        self.assertEqual(json.loads(flows[2].metadata_json), {
            "tool_call_id": "demo-call-1", "status": "completed", "turn_id": "turn:demo",
        })
        self.assertEqual(assistant_message.metadata_json["structured_result"], card)

    async def test_demo_scope_rejects_model_forged_candidates_before_provider_replay(self):
        provider = SimpleNamespace(
            get_default_model=lambda: "scripted-model",
            chat_with_retry=AsyncMock(return_value=LLMResponse(
                content=None, tool_calls=[ToolCallRequest(
                    id="forged-call", name="prioritize_followups",
                    arguments={"candidates": [{"candidate_id": "foreign-private-policy"}]},
                )], finish_reason="tool_calls",
            )),
        )
        self.runtime.agent_loop = AgentLoop(
            MessageBus(), provider, Path(self.folder.name),
            tool_registry=build_reasoning_registry(Path(self.folder.name)),
        )
        with patch.dict(os.environ, {"M1_COURSEWORK_DEMO_TENANT_ID": "demo-tenant"}):
            socket, _ = await self.authenticate(self.token_demo)
            await socket.send({"message": "Prioritize", "agent_id": "AGT00690"})
            response = await socket.next()
        self.assertEqual(response["content"], "Invalid follow-up tool request.")
        self.assertNotIn("result", response)
        self.assertNotIn("foreign-private-policy", json.dumps(response))
        self.assertEqual(provider.chat_with_retry.await_count, 1)
        async with self.sessions() as db:
            audit = (await db.scalars(select(AiAuditLog))).one()
            flow = (await db.scalars(select(FlowLog).where(FlowLog.step_type == "tool_call"))).one()
        self.assertEqual(json.loads(audit.tools_called), ["prioritize_followups"])
        self.assertEqual(json.loads(flow.metadata_json)["status"], "invalid_parameters")
        self.assertNotIn("foreign-private-policy", audit.ai_response)

    async def test_demo_ordinary_chat_keeps_text_response_without_card(self):
        provider = SimpleNamespace(
            get_default_model=lambda: "scripted-model",
            chat_with_retry=AsyncMock(return_value=LLMResponse(content="Hello, agent.")),
        )
        self.runtime.agent_loop = AgentLoop(
            MessageBus(), provider, Path(self.folder.name),
            tool_registry=build_reasoning_registry(Path(self.folder.name)),
        )
        with patch.dict(os.environ, {"M1_COURSEWORK_DEMO_TENANT_ID": "demo-tenant"}):
            socket, _ = await self.authenticate(self.token_demo)
            await socket.send({"message": "Hello", "agent_id": "AGT00690"})
            response = await socket.next()
        self.assertEqual(response["content"], "Hello, agent.")
        self.assertNotIn("result", response)
        async with self.sessions() as db:
            audit = (await db.scalars(select(AiAuditLog))).one()
        self.assertEqual(audit.tools_called, "[]")

    async def test_malformed_demo_candidate_is_never_offered_or_ranked(self):
        source_file = Path(__file__).resolve().parents[1] / "data/evaluation/m2_candidate_scenarios.json"
        dataset = json.loads(source_file.read_text(encoding="utf-8"))
        dataset["scenarios"][0]["candidates"][0]["owner_agent_id"] = "foreign-agent"
        malformed = Path(self.folder.name) / "malformed-candidates.json"
        malformed.write_text(json.dumps(dataset), encoding="utf-8")
        provider = SimpleNamespace(
            get_default_model=lambda: "scripted-model",
            chat_with_retry=AsyncMock(return_value=LLMResponse(
                content=None, tool_calls=[ToolCallRequest(
                    id="malformed-call", name="prioritize_followups", arguments={},
                )], finish_reason="tool_calls",
            )),
        )
        self.runtime.agent_loop = AgentLoop(
            MessageBus(), provider, Path(self.folder.name),
            tool_registry=build_reasoning_registry(Path(self.folder.name)),
            coursework_source=CourseworkCandidateSource(malformed, source_file.parents[1] / "mock"),
        )
        with patch.dict(os.environ, {"M1_COURSEWORK_DEMO_TENANT_ID": "demo-tenant"}):
            socket, _ = await self.authenticate(self.token_demo)
            await socket.send({"message": "Prioritize", "agent_id": "AGT00690"})
            response = await socket.next()
        self.assertEqual(response["content"], "Verified follow-up candidates are unavailable.")
        self.assertNotIn("result", response)
        offered = provider.chat_with_retry.await_args_list[0].kwargs["tools"]
        self.assertNotIn("prioritize_followups", [row["function"]["name"] for row in offered])

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
