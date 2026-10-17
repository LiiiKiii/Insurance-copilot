"""Agent assessment and allowance status model."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from admin.db import Base
from admin.utils import now_beijing


class AgentAssessment(Base):
    """Store one assessment subject for an agent within a tenant."""

    __tablename__ = "agent_assessments"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=True, index=True
    )
    agent_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(64), nullable=False)
    target_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_beijing, onupdate=now_beijing
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "agent_id",
            "subject",
            name="uq_assessment_agent_subject",
        ),
        Index("idx_assessment_agent", "tenant_id", "agent_id"),
    )
