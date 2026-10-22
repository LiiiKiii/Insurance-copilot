"""Authenticated chat-session listing, history, and deletion endpoints."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, status
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from admin.dependencies import DB, CurrentUser, _error
from admin.models.chat_session import ChatMessage, ChatSession


logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat-sessions"])


def _decode_metadata(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        logger.warning("Ignoring malformed chat-message metadata")
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _session_payload(session: ChatSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "agent_id": session.agent_id,
        "title": session.title,
        "updated_at": session.updated_at.isoformat() if session.updated_at else "",
        "created_at": session.created_at.isoformat() if session.created_at else "",
        "last_message_at": (
            session.last_message_at.isoformat() if session.last_message_at else ""
        ),
        "message_count": session.message_count or 0,
    }


@router.get("/api/chat-sessions")
async def list_chat_sessions(current_user: CurrentUser, db: DB) -> dict[str, Any]:
    rows = (
        await db.scalars(
            select(ChatSession)
            .where(ChatSession.user_id == current_user.id)
            .order_by(
                ChatSession.last_message_at.desc(),
                ChatSession.updated_at.desc(),
                ChatSession.id.desc(),
            )
            .limit(100)
        )
    ).all()
    return {"ok": True, "data": [_session_payload(row) for row in rows]}


@router.get("/api/chat-sessions/{session_id}")
async def get_chat_session(
    session_id: str,
    current_user: CurrentUser,
    db: DB,
) -> dict[str, Any]:
    session = (
        await db.scalars(
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .where(
                ChatSession.id == session_id,
                ChatSession.user_id == current_user.id,
            )
        )
    ).one_or_none()
    if session is None:
        raise _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Session not found")

    return {
        "ok": True,
        "data": {
            **_session_payload(session),
            "messages": [
                {
                    "id": message.id,
                    "role": message.role,
                    "content": message.content,
                    "timestamp": (
                        message.created_at.isoformat() if message.created_at else ""
                    ),
                    "metadata": _decode_metadata(message.metadata_json),
                }
                for message in session.messages
            ],
        },
    }


@router.delete("/api/chat-sessions/{session_id}")
async def delete_chat_session(
    session_id: str,
    current_user: CurrentUser,
    db: DB,
) -> dict[str, Any]:
    owned_session = await db.scalar(
        select(ChatSession.id).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    if owned_session is None:
        raise _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Session not found")

    await db.execute(delete(ChatMessage).where(ChatMessage.session_id == session_id))
    await db.execute(
        delete(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    await db.commit()
    return {"ok": True, "data": {"message": "Session deleted"}}
