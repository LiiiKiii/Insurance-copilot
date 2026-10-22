"""Persistence helpers shared by the chat HTTP and WebSocket transports."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from admin.models.chat import ChatMessage, ChatSession
from admin.models.user import User
from admin.utils import now_beijing


def _title(message: str) -> str:
    compact = " ".join(message.split())
    return (compact[:77] + "...") if len(compact) > 80 else (compact or "New Chat")


async def persist_turn(
    db: AsyncSession,
    *,
    session_id: str,
    user: User,
    agent_id: str,
    user_message: str,
    assistant_message: str,
    user_metadata: dict[str, Any] | None = None,
    assistant_metadata: dict[str, Any] | None = None,
) -> None:
    """Create or update one user-owned session and append a complete turn."""
    session = await db.get(ChatSession, session_id)
    now = now_beijing()
    if session is None:
        session = ChatSession(
            id=session_id,
            tenant_id=user.tenant_id,
            user_id=user.id,
            agent_id=agent_id,
            title=_title(user_message),
            created_at=now,
            updated_at=now,
            last_message_at=now,
            message_count=0,
        )
        db.add(session)
    elif (
        session.user_id != user.id
        or session.tenant_id != user.tenant_id
        or session.agent_id != agent_id
    ):
        raise PermissionError("Chat session ownership does not match the caller")

    session.updated_at = now
    session.last_message_at = now
    session.message_count = (session.message_count or 0) + 2
    db.add_all(
        [
            ChatMessage(
                session_id=session_id,
                role="user",
                content=user_message,
                metadata_json=user_metadata,
                created_at=now,
            ),
            ChatMessage(
                session_id=session_id,
                role="assistant",
                content=assistant_message,
                metadata_json=assistant_metadata,
                created_at=now + timedelta(microseconds=1),
            ),
        ]
    )
    await db.commit()


async def list_sessions(db: AsyncSession, user: User) -> list[dict[str, Any]]:
    counts = (
        select(ChatMessage.session_id, func.count(ChatMessage.id).label("message_count"))
        .group_by(ChatMessage.session_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(ChatSession, func.coalesce(counts.c.message_count, 0))
            .outerjoin(counts, counts.c.session_id == ChatSession.id)
            .where(
                ChatSession.tenant_id == user.tenant_id,
                ChatSession.user_id == user.id,
            )
            .order_by(ChatSession.last_message_at.desc(), ChatSession.id.asc())
        )
    ).all()
    return [
        {
            "id": session.id,
            "agent_id": session.agent_id,
            "title": session.title,
            "updated_at": session.updated_at.isoformat() if session.updated_at else None,
            "message_count": int(message_count),
        }
        for session, message_count in rows
    ]


async def load_session(
    db: AsyncSession, user: User, session_id: str
) -> tuple[ChatSession | None, list[dict[str, Any]]]:
    session = await db.get(ChatSession, session_id)
    if session is None or session.user_id != user.id or session.tenant_id != user.tenant_id:
        return None, []
    rows = (
        await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        )
    ).scalars().all()
    return session, [
        {
            "id": row.id,
            "role": row.role,
            "content": row.content,
            "timestamp": row.created_at.isoformat() if row.created_at else None,
            "metadata": row.metadata_json,
        }
        for row in rows
    ]
