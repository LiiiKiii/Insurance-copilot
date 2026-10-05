"""Deterministic annual performance pace calculations for the A2 reasoning layer."""

from datetime import date


AVG_DAYS_PER_MONTH = 30.44
DEFAULT_PERIOD_MONTHS = 12
PACE_ON_TRACK = 1.0
PACE_BEHIND = 0.85
PACE_AT_RISK = 0.6


def compute_run_rate(
    current: float,
    target: float,
    period_start: str | None = None,
    as_of_date: str | None = None,
) -> dict:
    """Calculate current pace and projected annual attainment."""
    if target <= 0:
        raise ValueError("target must be greater than zero")

    today = date.fromisoformat(as_of_date) if as_of_date else date.today()
    start = (
        date.fromisoformat(period_start)
        if period_start
        else date(today.year, 1, 1)
    )

    months_elapsed = max((today - start).days / AVG_DAYS_PER_MONTH, 0.5)
    months_remaining = max(DEFAULT_PERIOD_MONTHS - months_elapsed, 0.5)
    monthly_avg = round(current / months_elapsed)
    gap = max(target - current, 0)
    monthly_needed = round(gap / months_remaining) if gap > 0 else 0
    projected_year_end = round(current + monthly_avg * months_remaining)
    projected_rate = round(projected_year_end / target, 3)

    if projected_rate >= PACE_ON_TRACK:
        pace_status = "on_track"
        pace_label = "On track"
    elif projected_rate >= PACE_BEHIND:
        pace_status = "behind"
        pace_label = "Behind pace"
    elif projected_rate >= PACE_AT_RISK:
        pace_status = "at_risk"
        pace_label = "At risk"
    else:
        pace_status = "critical"
        pace_label = "Critical pace gap"

    if gap > 0:
        narrative = (
            f"Current average is {monthly_avg:,} per month; "
            f"{monthly_needed:,} per month is required to reach the target. "
            f"Projected attainment is {projected_rate:.1%}."
        )
    else:
        narrative = "Target already achieved."

    return {
        "current": current,
        "target": target,
        "months_elapsed": round(months_elapsed, 1),
        "months_remaining": round(months_remaining, 1),
        "monthly_avg": monthly_avg,
        "monthly_needed": monthly_needed,
        "projected_year_end": projected_year_end,
        "projected_rate": projected_rate,
        "pace_status": pace_status,
        "pace_label": pace_label,
        "narrative": narrative,
    }
