"""Shared database helpers for insurance data-layer tools."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

from admin.db import get_sync_db
from admin.models.agent_data import AgentAttribution, AgentPerformanceMetrics
from admin.models.competition import Competition, CompetitionEntry

logger = logging.getLogger(__name__)


def db_error(exc: Exception) -> str:
    """Return a stable JSON response for database failures."""
    logger.error("Database query failed: %s", exc)
    return json.dumps({"error": "Database query failed"})


def load_performance_row(agent_id: str) -> AgentPerformanceMetrics | None:
    """Return the latest performance row for an agent.

    Scalar attributes remain available after the session closes because the
    synchronous session factory uses ``expire_on_commit=False``.
    """
    with get_sync_db() as db:
        return (
            db.query(AgentPerformanceMetrics)
            .filter(AgentPerformanceMetrics.agent_id == agent_id)
            .order_by(AgentPerformanceMetrics.period_end.desc())
            .first()
        )


def load_attribution_row(agent_id: str) -> AgentAttribution | None:
    """Return the attribution snapshot for an agent."""
    with get_sync_db() as db:
        return (
            db.query(AgentAttribution)
            .filter(AgentAttribution.agent_id == agent_id)
            .first()
        )


def load_competitions_from_db(
    workspace: Path,
    agent_id: str,
) -> list[dict[str, Any]]:
    """Return active competitions and entries for an agent.

    The workspace parameter keeps the helper compatible with the planning
    layer and leaves room for workspace-specific configuration in later
    milestones.
    """
    del workspace

    with get_sync_db() as db:
        rows = (
            db.query(
                Competition.id,
                Competition.name,
                Competition.name_en,
                Competition.type,
                Competition.target_metric,
                Competition.target_value,
                Competition.unit,
                Competition.deadline,
                Competition.reward,
                Competition.description,
                CompetitionEntry.current_value,
                CompetitionEntry.gap,
                CompetitionEntry.status,
            )
            .join(
                CompetitionEntry,
                CompetitionEntry.competition_id == Competition.id,
            )
            .filter(
                CompetitionEntry.agent_id == agent_id,
                Competition.is_active.is_(True),
            )
            .order_by(Competition.deadline)
            .all()
        )

    today = date.today()
    competitions: list[dict[str, Any]] = []
    for row in rows:
        current = row.current_value
        gap = row.gap
        target = (
            current + gap
            if current is not None and gap is not None
            else row.target_value
        )

        try:
            deadline = datetime.strptime(row.deadline, "%Y-%m-%d").date()
            days_remaining: int | None = (deadline - today).days
        except (TypeError, ValueError):
            days_remaining = None
            logger.warning(
                "Unable to parse deadline %r for competition %s",
                row.deadline,
                row.id,
            )

        competitions.append(
            {
                "id": row.id,
                "name": row.name,
                "name_en": row.name_en,
                "type": row.type,
                "target_metric": row.target_metric,
                "target_value": target,
                "current_value": current,
                "gap": gap,
                "unit": row.unit,
                "deadline": row.deadline,
                "days_remaining": days_remaining,
                "tags": [],
                "status": row.status or "",
                "reward": row.reward,
                "description": row.description,
            }
        )

    return competitions
