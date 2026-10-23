"""Pure presentation enrichment for the legacy competition API contract."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

logger = logging.getLogger(__name__)

AVG_DAYS_PER_MONTH = 30.44
URGENCY_CRITICAL_DAYS = 30
URGENCY_IMPORTANT_DAYS = 90
EASY_TAG_GAP_RATIO = 0.2
PROBABILITY_THRESHOLDS = (
    (1.5, 95),
    (1.0, 80),
    (0.7, 55),
    (0.4, 30),
)


def enrich_competitions(
    competitions: list[dict[str, Any]],
    *,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Return UI-ready copies without mutating shared database results."""
    today = today or date.today()
    months_elapsed = max((today - date(today.year, 1, 1)).days / AVG_DAYS_PER_MONTH, 1)
    enriched: list[dict[str, Any]] = []

    for competition in competitions:
        item = dict(competition)
        try:
            deadline = datetime.strptime(str(item["deadline"]), "%Y-%m-%d").date()
            days_remaining: int | None = (deadline - today).days
        except (KeyError, TypeError, ValueError):
            logger.warning(
                "Competition %s has an invalid deadline",
                item.get("id", "unknown"),
            )
            deadline = None
            days_remaining = None

        item["days_remaining"] = days_remaining
        if days_remaining is not None and days_remaining <= URGENCY_CRITICAL_DAYS:
            item["urgency_level"] = "critical"
        elif days_remaining is not None and days_remaining <= URGENCY_IMPORTANT_DAYS:
            item["urgency_level"] = "important"
        else:
            item["urgency_level"] = "normal"

        gap = item.get("gap")
        target = item.get("target_value") or 0
        current = item.get("current_value") or 0
        tags = set(item.get("tags") or [])
        if (
            days_remaining is not None
            and days_remaining <= URGENCY_CRITICAL_DAYS
            and gap is not None
            and gap > 0
        ):
            tags.add("Urgent")
        if gap is not None and target > 0 and gap <= target * EASY_TAG_GAP_RATIO:
            tags.add("Easy")
        item["tags"] = sorted(tags)

        if gap is not None and gap <= 0:
            item["feasibility_hint"] = "Achieved"
            item["feasibility_analysis"] = None
        elif (
            gap is not None
            and gap > 0
            and days_remaining is not None
            and days_remaining > 0
            and target > 0
        ):
            months_to_deadline = max(days_remaining / AVG_DAYS_PER_MONTH, 0.5)
            monthly_run_rate = current / months_elapsed
            monthly_needed = gap / months_to_deadline
            if monthly_run_rate <= 0:
                probability = 5
            else:
                ratio = monthly_run_rate / monthly_needed if monthly_needed > 0 else float("inf")
                probability = 10
                for threshold, candidate in PROBABILITY_THRESHOLDS:
                    if ratio >= threshold:
                        probability = candidate
                        break

            gap_ratio = gap / target
            if gap_ratio <= EASY_TAG_GAP_RATIO or probability >= 70:
                hint = "Achievable"
            elif probability >= 40:
                hint = "Challenging"
            else:
                hint = "Very difficult"
            item["feasibility_hint"] = hint
            item["feasibility_analysis"] = {
                "monthly_run_rate": round(monthly_run_rate),
                "monthly_needed": round(monthly_needed),
                "net_gap_after_pending": round(gap),
                "pipeline_status": "not_applicable",
                "pipeline_coverage_pct": 0,
                "estimated_probability_pct": probability,
            }
        else:
            item["feasibility_hint"] = "Not applicable"
            item["feasibility_analysis"] = None

        enriched.append(item)

    urgency_order = {"critical": 0, "important": 1, "normal": 2}

    def sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
        gap = item.get("gap")
        complete = gap is not None and gap <= 0
        try:
            deadline = datetime.strptime(str(item["deadline"]), "%Y-%m-%d").date()
        except (KeyError, TypeError, ValueError):
            deadline = date.max
        return (
            1 if complete else 0,
            urgency_order.get(item.get("urgency_level", "normal"), 2),
            deadline,
            gap if gap is not None else float("inf"),
        )

    enriched.sort(key=sort_key)
    return enriched
