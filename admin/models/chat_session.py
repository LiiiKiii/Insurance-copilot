"""Persisted chat sessions and their user/assistant messages."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from admin.db import Base
from admin.utils import now_beijing


class ChatSession(Base):
    """One user-owned conversation displayed in the chat sidebar."""

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), default="New Chat", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_beijing, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now_beijing,
        onupdate=now_beijing,
        nullable=False,
        index=True,
    )
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_beijing, nullable=False, index=True
    )
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    messages: Mapped[list[ChatMessage]] = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="(ChatMessage.created_at, ChatMessage.id)",
    )


class ChatMessage(Base):
    """One persisted message and its optional structured UI metadata."""

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_beijing, nullable=False, index=True
    )

    session: Mapped[ChatSession] = relationship(
        "ChatSession", back_populates="messages"
    )
