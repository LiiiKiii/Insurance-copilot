"""Inbox messages, daily briefings, and tenant briefing settings."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from admin.db import Base
from admin.utils import now_beijing


class InboxMessage(Base):
    """A customer notification received from an external system."""

    __tablename__ = "inbox_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    # Agent ownership uses the existing username identifier to avoid coupling
    # the external message feed directly to users.id.
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    priority: Mapped[str] = mapped_column(String(8), nullable=False)  # P0|P1|P2
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    notification_name: Mapped[str] = mapped_column(String(128), nullable=False)
    receiver_type: Mapped[str] = mapped_column(String(64), nullable=False)

    trigger_logic: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    policy_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    business_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    classify_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel: Mapped[str] = mapped_column(String(16), nullable=False, default="sms")

    deadline_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_beijing)
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_beijing)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    source_system: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing, onupdate=now_beijing)

    __table_args__ = (
        UniqueConstraint("tenant_id", "external_id", name="uq_inbox_external"),
        Index("idx_inbox_tenant_agent_time", "tenant_id", "agent_id", "occurred_at"),
        Index("idx_inbox_priority", "tenant_id", "agent_id", "priority", "occurred_at"),
    )


class DailyBriefing(Base):
    """An AI-generated snapshot unique to a tenant, agent, and date."""

    __tablename__ = "daily_briefings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False)
    briefing_date: Mapped[date] = mapped_column(Date, nullable=False)

    message_count: Mapped[int] = mapped_column(Integer, default=0)
    p0_count: Mapped[int] = mapped_column(Integer, default=0)
    p1_count: Mapped[int] = mapped_column(Integer, default=0)
    p2_count: Mapped[int] = mapped_column(Integer, default=0)

    summary_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_items: Mapped[list | None] = mapped_column(JSON, nullable=True)
    message_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)

    model_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    model_display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    generated_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing, onupdate=now_beijing)

    __table_args__ = (
        UniqueConstraint("tenant_id", "agent_id", "briefing_date", name="uq_briefing_agent_date"),
    )


class BriefingSettings(Base):
    """Tenant-level scheduling settings for briefing warmup."""

    __tablename__ = "briefing_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False, unique=True)

    auto_generate_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # HH:MM in 24-hour Asia/Shanghai time.
    auto_generate_time: Mapped[str] = mapped_column(String(5), default="08:30")
    # all | active_7d | active_30d
    auto_generate_scope: Mapped[str] = mapped_column(String(16), default="active_7d")
    min_messages_to_generate: Mapped[int] = mapped_column(Integer, default=1)

    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_run_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_run_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing, onupdate=now_beijing)
