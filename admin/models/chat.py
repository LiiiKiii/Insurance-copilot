"""Persisted user-owned chat sessions and messages."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from admin.db import Base
from admin.utils import now_beijing


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (
        Index("idx_chat_session_owner_updated", "tenant_id", "user_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="New Chat")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_beijing, onupdate=now_beijing, index=True
    )
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_beijing, index=True
    )
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("idx_chat_message_session_created", "session_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing)

    session: Mapped[ChatSession] = relationship(back_populates="messages")
