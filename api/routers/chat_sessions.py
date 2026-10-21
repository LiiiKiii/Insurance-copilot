"""Authenticated chat-history endpoints consumed by the main workbench."""
from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import delete

from admin.dependencies import DB, CurrentUser, _error
from admin.models.chat import ChatMessage, ChatSession
from api.chat_history import list_sessions, load_session

router = APIRouter(prefix="/api/chat-sessions", tags=["chat-sessions"])


@router.get("")
async def get_chat_sessions(current_user: CurrentUser, db: DB) -> dict:
    return {"ok": True, "data": await list_sessions(db, current_user)}


@router.get("/{session_id}")
async def get_chat_session(
    session_id: str, current_user: CurrentUser, db: DB
) -> dict:
    session, messages = await load_session(db, current_user, session_id)
    if session is None:
        raise _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Chat session not found")
    return {
        "ok": True,
        "data": {
            "id": session.id,
            "agent_id": session.agent_id,
            "title": session.title,
            "messages": messages,
        },
    }


@router.delete("/{session_id}")
async def delete_chat_session(
    session_id: str, current_user: CurrentUser, db: DB
) -> dict:
    session = await db.get(ChatSession, session_id)
    if session is None or session.user_id != current_user.id or session.tenant_id != current_user.tenant_id:
        raise _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Chat session not found")
    await db.execute(delete(ChatMessage).where(ChatMessage.session_id == session_id))
    await db.delete(session)
    await db.commit()
    return {"ok": True, "data": {"id": session_id}}
