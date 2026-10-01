"""Performance-target model for administrator-managed agent KPIs."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from admin.db import Base
from admin.utils import now_beijing


class PerformanceTarget(Base):
    """Store one metric target for an agent and reporting period."""

    __tablename__ = "performance_targets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    metric_key: Mapped[str] = mapped_column(String(50), nullable=False)
    metric_label: Mapped[str] = mapped_column(String(100), default="")
    target_value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), default="HKD")
    period_type: Mapped[str] = mapped_column(String(20), default="annual")
    period_start: Mapped[str] = mapped_column(String(10), nullable=False)
    period_end: Mapped[str] = mapped_column(String(10), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now_beijing,
        onupdate=now_beijing,
    )
