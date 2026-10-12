"""Non-streaming WebSocket chat endpoint for the shared agent runtime."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.compliance import apply_compliance


router = APIRouter()
logger = logging.getLogger(__name__)


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
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string.")
    return value


def _valid_turn_id(payload: object) -> str | None:
    """Return a client turn ID only when it is safe to echo in an error."""
    if not isinstance(payload, dict):
        return None
    turn_id = payload.get("turn_id")
    return turn_id if isinstance(turn_id, str) and turn_id.strip() else None


def _get_agent_loop(websocket: WebSocket) -> Any | None:
    """Return an available shared loop without creating application state."""
    runtime = getattr(websocket.app.state, "runtime", None)
    if runtime is None or not getattr(runtime, "is_running", False):
        return None

    agent_loop = getattr(runtime, "agent_loop", None)
    if agent_loop is None or not callable(getattr(agent_loop, "process_direct", None)):
        return None
    return agent_loop


@router.websocket("/ws/chat")
async def chat(websocket: WebSocket) -> None:
    """Process multiple non-streaming chat requests over one connection.

    Client-supplied agent IDs are routing data only.  This endpoint deliberately
    does not claim to authenticate or authorize them; that boundary belongs to
    a future authentication integration.
    """
    await websocket.accept()
    connection_session_id: str | None = None

    while True:
        try:
            raw_request = await websocket.receive_text()
        except WebSocketDisconnect:
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

        try:
            session_id = _optional_identifier(
                payload,
                "session_id",
                connection_session_id or _new_session_id(),
            )
            turn_id = _optional_identifier(payload, "turn_id", _new_turn_id())
        except ValueError as exc:
            await websocket.send_json(_error(str(exc), _valid_turn_id(payload)))
            continue

        connection_session_id = session_id
        agent_loop = _get_agent_loop(websocket)
        if agent_loop is None:
            await websocket.send_json(
                _error("Agent runtime is unavailable.", turn_id)
            )
            continue

        try:
            result = await agent_loop.process_direct(
                content=message,
                session_key=session_id,
                channel="websocket",
                chat_id=agent_id,
            )
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

        processed_content, _, _ = apply_compliance(content)

        try:
            await websocket.send_json(
                {
                    "type": "response",
                    "content": processed_content,
                    "session_id": session_id,
                    "turn_id": turn_id,
                }
            )
        except WebSocketDisconnect:
            return
