"""Agent business-data models.

The tables cover performance metrics, pending policies, attribution snapshots,
client records, and agent profiles. They replace the legacy raw-SQL data layer
with database-independent SQLAlchemy models.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from admin.db import Base
from admin.utils import now_beijing


class AgentPerformanceMetrics(Base):
    """Store a complete set of performance metrics for one reporting period."""

    __tablename__ = "agent_performance_metrics"
    __table_args__ = (UniqueConstraint("agent_id", "period_start", "period_end"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    period_start: Mapped[str] = mapped_column(String(10), nullable=False)
    period_end: Mapped[str] = mapped_column(String(10), nullable=False)

    protection_premium_current: Mapped[float | None] = mapped_column(Float, nullable=True)
    protection_premium_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    protection_premium_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    pending_premium_current: Mapped[float | None] = mapped_column(Float, nullable=True)

    avg_case_size_current: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_case_size_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_case_size_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_case_size_peer_avg: Mapped[float | None] = mapped_column(Float, nullable=True)

    submission_count_current: Mapped[float | None] = mapped_column(Float, nullable=True)
    submission_count_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    submission_count_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    conversion_rate_current: Mapped[float | None] = mapped_column(Float, nullable=True)
    conversion_rate_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    conversion_rate_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    conversion_rate_peer_avg: Mapped[float | None] = mapped_column(Float, nullable=True)

    new_clients_current: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_clients_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_clients_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    client_retention_current: Mapped[float | None] = mapped_column(Float, nullable=True)
    client_retention_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    client_retention_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    ai_training_usage_current: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_training_usage_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_training_usage_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    fyc_current: Mapped[float | None] = mapped_column(Float, nullable=True)
    fyc_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    fyc_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    history_last_month_pp: Mapped[float | None] = mapped_column(Float, nullable=True)
    history_last_quarter_pp: Mapped[float | None] = mapped_column(Float, nullable=True)
    history_last_year_pp: Mapped[float | None] = mapped_column(Float, nullable=True)

    ranking_team_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ranking_team_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ranking_region_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ranking_region_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ranking_team_percentile: Mapped[float | None] = mapped_column(Float, nullable=True)
    ranking_top_performer_premium: Mapped[float | None] = mapped_column(Float, nullable=True)

    team_personal_premium: Mapped[float | None] = mapped_column(Float, nullable=True)
    team_subordinate_premium: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Attachment 2, dimension 5: conversion output and productivity.
    policy_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quarter_fyc: Mapped[float | None] = mapped_column(Float, nullable=True)
    ytd_fyc: Mapped[float | None] = mapped_column(Float, nullable=True)
    daily_fyc: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Attachment 2, dimension 7: client portfolio and retention.
    total_clients: Mapped[int | None] = mapped_column(Integer, nullable=True)
    churn_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    churn_clients: Mapped[int | None] = mapped_column(Integer, nullable=True)
    renewal_due_clients: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Attachment 2, dimension 9: learning and compliance.
    ai_practice_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    online_university: Mapped[str | None] = mapped_column(String(20), nullable=True)
    no_train_no_sell: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        default=now_beijing,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        default=now_beijing,
        onupdate=now_beijing,
    )


class AgentPolicy(Base):
    """Store a submitted policy and its underwriting status."""

    __tablename__ = "agent_policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    policy_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    client_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    customer_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    premium: Mapped[float | None] = mapped_column(Float, nullable=True)
    product: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status_detail: Mapped[str | None] = mapped_column(String(200), nullable=True)
    submit_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    est_days_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    est_days_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_beijing)


class AgentAttribution(Base):
    """Store the latest structured attribution snapshot for an agent."""

    __tablename__ = "agent_attribution"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    period: Mapped[str | None] = mapped_column(String(50), nullable=True)
    data_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_beijing)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=now_beijing,
        onupdate=now_beijing,
    )


class AgentClient(Base):
    """Store an agent's core clients and segmentation tags."""

    __tablename__ = "agent_clients"
    __table_args__ = (UniqueConstraint("agent_id", "client_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    premium: Mapped[float | None] = mapped_column(Float, nullable=True)
    tag_categories: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tag_labels: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_beijing)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=now_beijing,
        onupdate=now_beijing,
    )


class AgentProfile(Base):
    """Store an agent's business profile and contact information."""

    __tablename__ = "agent_profiles"

    agent_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name_en: Mapped[str | None] = mapped_column(String(100), nullable=True)
    license_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    team: Mapped[str | None] = mapped_column(String(100), nullable=True)
    join_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    specialties: Mapped[str | None] = mapped_column(Text, nullable=True)
    years_of_service: Mapped[float | None] = mapped_column(Float, nullable=True)
    rank_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(100), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_beijing)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=now_beijing,
        onupdate=now_beijing,
    )
