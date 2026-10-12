"""Structured compliance checker for daily briefing.

Reads an agent's training/compliance status from `agent_performance_metrics`
and returns a list of structured warnings. Kept separate from the LLM-driven
briefing so compliance is always visible regardless of inbox messages.
"""
from __future__ import annotations

import logging
from typing import Literal

logger = logging.getLogger(__name__)

# Thresholds
AI_PRACTICE_WARN_THRESHOLD = 0.6

Level = Literal["error", "warning", "info"]


def _fetch_metrics(agent_id: str) -> dict | None:
    """Load latest agent_performance_metrics row for compliance fields."""
    try:
        from admin.db import get_sync_db
        from admin.models.agent_data import AgentPerformanceMetrics

        with get_sync_db() as db:
            m = (
                db.query(AgentPerformanceMetrics)
                .filter(AgentPerformanceMetrics.agent_id == agent_id)
                .order_by(AgentPerformanceMetrics.period_end.desc())
                .first()
            )
            if not m:
                return None
            return {
                "no_train_no_sell": bool(m.no_train_no_sell),
                "online_university": m.online_university,
                "ai_practice_rate": m.ai_practice_rate,
                "ai_training_usage": m.ai_training_usage_current,
            }
    except Exception as e:
        logger.debug(f"Failed to fetch compliance for {agent_id}: {e}")
        return None


def get_compliance_warnings(agent_id: str) -> list[dict]:
    """Return a structured list of compliance warnings for an agent.

    Each item: {type, level, title, message}.
    Returns [] if no issues or if data unavailable.
    """
    data = _fetch_metrics(agent_id)
    if not data:
        return []

    warnings: list[dict] = []

    if data["no_train_no_sell"]:
        warnings.append({
            "type": "no_train_no_sell",
            "level": "error",
            "title": "Whole-life product sales restriction",
            "message": (
                "Required training is incomplete, so whole-life products cannot "
                "currently be sold. Other product categories are unaffected. "
                "Complete the online training to remove this restriction."
            ),
        })

    university = data["online_university"]
    completed_statuses = {"completed", "complete", "\u5df2\u5b8c\u6210"}
    if university and str(university).strip().casefold() not in completed_statuses:
        warnings.append({
            "type": "online_university_incomplete",
            "level": "warning",
            "title": "Online training is incomplete",
            "message": f"Current online training status: {university}. Please complete it promptly.",
        })

    ai_rate = data["ai_practice_rate"]
    if ai_rate is not None and ai_rate < AI_PRACTICE_WARN_THRESHOLD:
        warnings.append({
            "type": "ai_practice_low",
            "level": "warning",
            "title": "AI practice completion is low",
            "message": (
                f"Current completion is {ai_rate*100:.0f}%. Increase it to at "
                f"least {AI_PRACTICE_WARN_THRESHOLD*100:.0f}%."
            ),
        })

    return warnings
