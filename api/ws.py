"""Non-streaming WebSocket chat endpoint for the shared agent runtime."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from admin.db import AsyncSessionFactory
from admin.dependencies import authenticate_access_token
from admin.hooks import log_ai_audit, log_flow_step
from admin.models.tenant import Tenant
from api.chat_history import persist_turn
from api.compliance import apply_compliance
from nanobot.agent.coursework_demo import CourseworkDemoScope
from nanobot.bus.events import OutboundMessage

router = APIRouter()
logger = logging.getLogger(__name__)
_AUTH_TIMEOUT_SECONDS = 5
_MAX_AUTH_FRAME_BYTES = 8192
_MAX_SESSION_ALIASES = 64
_TOOL_NAME = re.compile(r"[a-z][a-z0-9_]{0,99}\Z")
_TOOL_CALL_ID = re.compile(r"[A-Za-z0-9._:-]{1,100}\Z")
_TOOL_STATUSES = frozenset({
    "completed", "unknown_tool", "invalid_parameters", "timed_out",
    "execution_failed", "agent_access_denied",
    "candidate_source_unavailable", "result_too_large",
})


def _new_session_id() -> str:
    """Return a session identifier in the WebSocket namespace."""
    return f"ws:{uuid4().hex}"


def _new_turn_id() -> str:
    """Return a unique identifier for one WebSocket request."""
    return f"turn:{uuid4().hex}"


def _error(content: str, turn_id: str | None = None) -> dict[str, str]:
    """Build a client-safe error event, retaining a valid correlation ID."""
    event = {"type": "error", "content": content}
    if turn_id is not None:
        event["turn_id"] = turn_id
    return event


def _optional_identifier(
    payload: dict[str, Any],
    field: str,
    generated: str,
) -> str:
    """Read a non-empty optional string identifier or return its default."""
    value = payload.get(field)
    if value is None:
        return generated
    if not isinstance(value, str) or not value.strip() or len(value) > 100:
        raise ValueError(f"{field} must be a non-empty string.")
    return value


def _valid_turn_id(payload: object) -> str | None:
    """Return a client turn ID only when it is safe to echo in an error."""
    if not isinstance(payload, dict):
        return None
    turn_id = payload.get("turn_id")
    return turn_id if isinstance(turn_id, str) and turn_id.strip() and len(turn_id) <= 100 else None


def _get_agent_loop(websocket: WebSocket) -> Any | None:
    """Return an available shared loop without creating application state."""
    runtime = getattr(websocket.app.state, "runtime", None)
    if runtime is None or not getattr(runtime, "is_running", False):
        return None

    agent_loop = getattr(runtime, "agent_loop", None)
    if agent_loop is None or not callable(getattr(agent_loop, "process_direct", None)):
        return None
    return agent_loop


def _origin_allowed(websocket: WebSocket) -> bool:
    """Allow same-origin browser sockets or an explicit deployment allowlist."""
    origin = websocket.headers.get("origin")
    if origin is None:
        return True  # Non-browser clients still require the JWT handshake.
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
        return False
    allowed = {item.strip().rstrip("/") for item in os.getenv("WS_ALLOWED_ORIGINS", "").split(",") if item.strip()}
    if origin in allowed:
        return True
    expected_scheme = "https" if websocket.scope.get("scheme") == "wss" else "http"
    if parsed.scheme != expected_scheme:
        return False
    host = websocket.headers.get("host")
    same_origin = host is not None and parsed.netloc.casefold() == host.casefold()
    if same_origin:
        return True
    # During local development the browser runs on :3000 while the API and
    # WebSocket server run on :8000.  Restrict this exception to loopback hosts
    # so a remote Origin can never use the relaxed port check.
    loopback_hosts = {"localhost", "127.0.0.1", "::1"}
    api_hostname = urlsplit(f"//{host}").hostname if host else None
    return parsed.hostname in loopback_hosts and api_hostname in loopback_hosts


async def _verified_user(token: str):
    async with AsyncSessionFactory() as db:
        return await authenticate_access_token(token, db)


async def _coursework_demo_scope(user: Any) -> CourseworkDemoScope | None:
    """Map a live JWT principal to the explicitly configured demo tenant."""
    configured = os.getenv("M1_COURSEWORK_DEMO_TENANT_ID", "").strip()
    if not configured or user.tenant_id != configured:
        return None
    try:
        async with AsyncSessionFactory() as db:
            tenant = await db.get(Tenant, user.tenant_id)
        if tenant is None or not tenant.enabled or tenant.slug != "coursework-demo":
            return None
    except Exception:
        logger.warning("Coursework demo tenant validation failed")
        return None
    return CourseworkDemoScope(tenant_id=user.tenant_id, agent_id=user.username)


async def _audit_write(operation, **kwargs) -> None:
    try:
        await operation(**kwargs)
    except Exception:
        logger.warning("WebSocket audit persistence failed")


async def _persist_chat_turn(**kwargs) -> None:
    try:
        async with AsyncSessionFactory() as db:
            await persist_turn(db, **kwargs)
    except Exception:
        logger.warning("Chat-history persistence failed", exc_info=True)


def _auditable_tool_events(result: Any) -> list[dict[str, str]]:
    """Keep only bounded, non-sensitive tool trace fields from an Agent result."""
    metadata = getattr(result, "metadata", None)
    raw = metadata.get("tool_events") if isinstance(metadata, dict) else None
    if not isinstance(raw, list):
        return []
    events: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name, status = item.get("name"), item.get("status")
        if (not isinstance(name, str) or not _TOOL_NAME.fullmatch(name)
                or not isinstance(status, str) or status not in _TOOL_STATUSES):
            continue
        event = {"name": name, "status": status}
        call_id = item.get("tool_call_id")
        if isinstance(call_id, str) and _TOOL_CALL_ID.fullmatch(call_id):
            event["tool_call_id"] = call_id
        events.append(event)
    return events


def _structured_recommendation(result: Any, events: list[dict[str, str]]) -> dict[str, Any] | None:
    """Expose only a completed, correlated internal coursework tool result."""
    if not isinstance(result, OutboundMessage):
        return None
    value = result.metadata.get("structured_result")
    if not isinstance(value, dict) or value.get("kind") != "action_plan":
        return None
    call_id = value.get("tool_call_id")
    if (not isinstance(call_id, str) or not _TOOL_CALL_ID.fullmatch(call_id)
            or not any(event.get("name") == "prioritize_followups"
                       and event.get("status") == "completed"
                       and event.get("tool_call_id") == call_id for event in events)
            or value.get("source") != "m2-coursework-candidates-v3"):
        return None
    actions = value.get("actions")
    if not isinstance(actions, list) or not 1 <= len(actions) <= 50:
        return None
    for rank, action in enumerate(actions, start=1):
        if not isinstance(action, dict) or action.get("rank") != rank:
            return None
        if action.get("priority") not in {"P0", "P1", "P2"}:
            return None
        if not all(isinstance(action.get(key), str) and action[key].strip()
                   for key in ("candidate_id", "action", "timing")):
            return None
        score = action.get("priority_score")
        if (isinstance(score, bool) or not isinstance(score, (int, float))
                or not 0 <= score <= 100 or not math.isfinite(score)
                or not isinstance(action.get("evidence"), dict)
                or not isinstance(action.get("score_components"), dict)):
            return None
    return value


def _model_id(agent_loop: Any) -> str | None:
    configured = getattr(agent_loop, "model", None)
    if isinstance(configured, str) and configured:
        return configured
    provider = getattr(agent_loop, "provider", None)
    getter = getattr(provider, "get_default_model", None)
    if callable(getter):
        actual = getter()
        return actual if isinstance(actual, str) and actual else None
    return None


@router.websocket("/ws/chat")
async def chat(websocket: WebSocket) -> None:
    """Process authenticated non-streaming turns over one connection."""
    if not _origin_allowed(websocket):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        auth_frame = await asyncio.wait_for(websocket.receive_text(), _AUTH_TIMEOUT_SECONDS)
        if len(auth_frame.encode("utf-8")) > _MAX_AUTH_FRAME_BYTES:
            raise ValueError("Authentication frame too large")
        auth_payload = json.loads(auth_frame)
        if not isinstance(auth_payload, dict) or auth_payload.get("type") != "auth":
            raise ValueError("Authentication frame required")
        token = auth_payload.get("token")
        if not isinstance(token, str) or not token or len(token) > 4096:
            raise ValueError("Invalid authentication token")
        user = await _verified_user(token)
    except WebSocketDisconnect:
        return
    except Exception:
        await websocket.close(code=1008)
        return

    try:
        await websocket.send_json({"type": "auth_ok"})
    except WebSocketDisconnect:
        return
    session_aliases: dict[str, str] = {}
    connection_session_id = _new_session_id()

    while True:
        try:
            raw_request = await websocket.receive_text()
        except WebSocketDisconnect:
            return

        try:
            user = await _verified_user(token)
        except Exception:
            await websocket.close(code=1008)
            return

        try:
            payload = json.loads(raw_request)
        except json.JSONDecodeError:
            await websocket.send_json(_error("Invalid JSON payload."))
            continue

        turn_id = _valid_turn_id(payload)
        if not isinstance(payload, dict):
            await websocket.send_json(_error("Payload must be a JSON object."))
            continue

        message = payload.get("message")
        if not isinstance(message, str) or not message.strip():
            await websocket.send_json(
                _error("message must be a non-empty string.", turn_id)
            )
            continue

        agent_id = payload.get("agent_id")
        if not isinstance(agent_id, str) or not agent_id.strip():
            await websocket.send_json(
                _error("agent_id must be a non-empty string.", turn_id)
            )
            continue

        if agent_id != user.username:
            await websocket.send_json(_error("agent_id is not authorized.", turn_id))
            continue

        demo_scope = await _coursework_demo_scope(user)

        try:
            requested_session = _optional_identifier(
                payload,
                "session_id",
                connection_session_id,
            )
            turn_id = _optional_identifier(payload, "turn_id", _new_turn_id())
        except ValueError as exc:
            await websocket.send_json(_error(str(exc), _valid_turn_id(payload)))
            continue

        if requested_session in session_aliases.values():
            session_id = requested_session
        elif requested_session in session_aliases:
            session_id = session_aliases[requested_session]
        elif len(session_aliases) >= _MAX_SESSION_ALIASES:
            await websocket.send_json(_error("Too many sessions on this connection.", turn_id))
            continue
        else:
            session_id = _new_session_id()
            session_aliases[requested_session] = session_id
        connection_session_id = session_id
        turn_kwargs: dict[str, Any] = {
            "content": message, "session_key": session_id,
            "channel": "websocket", "chat_id": agent_id,
        }
        if demo_scope is not None:
            turn_kwargs["demo_scope"] = demo_scope
        await _audit_write(log_flow_step, session_id=session_id, agent_id=user.username,
                           step_index=0, step_type="user_input", content=message)
        try:
            coordinator = getattr(websocket.app.state, "runtime_apply_coordinator", None)
            if coordinator is None:
                agent_loop = _get_agent_loop(websocket)
                if agent_loop is None:
                    await websocket.send_json(_error("Agent runtime is unavailable.", turn_id))
                    continue
                model_id = _model_id(agent_loop)
                await _audit_write(log_flow_step, session_id=session_id, agent_id=user.username,
                                   step_index=1, step_type="llm_call", content=model_id or "")
                result = await agent_loop.process_direct(**turn_kwargs)
            else:
                async with coordinator.turn():
                    agent_loop = _get_agent_loop(websocket)
                    if agent_loop is None:
                        await websocket.send_json(_error("Agent runtime is unavailable.", turn_id))
                        continue
                    model_id = _model_id(agent_loop)
                    await _audit_write(log_flow_step, session_id=session_id, agent_id=user.username,
                                       step_index=1, step_type="llm_call", content=model_id or "")
                    result = await agent_loop.process_direct(**turn_kwargs)
        except WebSocketDisconnect:
            return
        except Exception as exc:
            logger.error(
                "WebSocket chat processing failed (%s)",
                type(exc).__name__,
            )
            await websocket.send_json(
                _error("Unable to process the message.", turn_id)
            )
            continue

        content = getattr(result, "content", None)
        if not isinstance(content, str):
            await websocket.send_json(
                _error("Agent returned no response.", turn_id)
            )
            continue

        processed_content, has_compliance_issue, matched_keywords = apply_compliance(content)
        tool_events = _auditable_tool_events(result)
        structured_result = _structured_recommendation(result, tool_events)

        await _persist_chat_turn(
            session_id=session_id,
            user=user,
            agent_id=agent_id,
            user_message=message,
            assistant_message=processed_content,
            assistant_metadata=dict(getattr(result, "metadata", None) or {}),
        )

        for index, event in enumerate(tool_events, start=2):
            await _audit_write(
                log_flow_step, session_id=session_id, agent_id=user.username,
                step_index=index, step_type="tool_call", content=event["name"],
                metadata_json=json.dumps({
                    "tool_call_id": event.get("tool_call_id"),
                    "status": event["status"],
                    "turn_id": turn_id,
                }),
            )
        await _audit_write(log_flow_step, session_id=session_id, agent_id=user.username,
                           step_index=2 + len(tool_events), step_type="response", content=processed_content)
        await _audit_write(
            log_ai_audit, session_id=session_id, agent_id=user.username,
            user_query=message, ai_response=processed_content,
            tools_called=json.dumps([event["name"] for event in tool_events]),
            model_id=model_id, has_compliance_issue=has_compliance_issue,
            compliance_notes=("Matched: " + ", ".join(matched_keywords)) if matched_keywords else None,
            tenant_id=user.tenant_id, user_id=user.id,
        )
        try:
            response_event: dict[str, Any] = {
                "type": "response", "content": processed_content,
                "session_id": session_id, "turn_id": turn_id,
            }
            if structured_result is not None:
                response_event["result"] = structured_result
            await websocket.send_json(response_event)
        except WebSocketDisconnect:
            return
