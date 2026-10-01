"""Competition models for competition definitions and per-agent progress."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from admin.db import Base
from admin.utils import now_beijing


class Competition(Base):
    """Define an incentive competition, honour, or certification target."""

    __tablename__ = "competitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    name_en: Mapped[str] = mapped_column(String(100), default="")
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_metric: Mapped[str] = mapped_column(String(50), nullable=False)
    target_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default="HKD")
    deadline: Mapped[str] = mapped_column(String(10), nullable=False)
    reward: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing)


class CompetitionEntry(Base):
    """Track one agent's progress in a competition."""

    __tablename__ = "competition_entries"
    __table_args__ = (
        UniqueConstraint("competition_id", "agent_id", name="uq_entry_comp_agent"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    competition_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("competitions.id"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    current_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    gap: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing)
