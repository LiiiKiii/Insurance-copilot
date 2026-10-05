"""Deterministic feasibility calculations for the A2 reasoning layer."""


DAYS_PER_MONTH_APPROX = 30

FEASIBILITY_RATIO_HIGH = 1.0
FEASIBILITY_RATIO_MEDIUM = 1.5
FEASIBILITY_RATIO_LOW = 2.5

FEASIBILITY_PROB_FLOOR = 5

FEASIBILITY_PROB_HIGH_BASE = 90
FEASIBILITY_PROB_HIGH_SCALE = 10
FEASIBILITY_PROB_HIGH_CAP = 95

FEASIBILITY_PROB_MEDIUM_BASE = 70
FEASIBILITY_PROB_MEDIUM_SCALE = 40

FEASIBILITY_PROB_LOW_BASE = 40
FEASIBILITY_PROB_LOW_SCALE = 20

FEASIBILITY_PROB_VLOW_BASE = 10
FEASIBILITY_PROB_VLOW_SCALE = 5

NON_HKD_WEEKLY_BASELINE = 3.0

NON_HKD_RATIO_HIGH = 1.0
NON_HKD_RATIO_MEDIUM = 2.0
NON_HKD_RATIO_LOW = 3.5

NON_HKD_PROB_HIGH_BASE = 90
NON_HKD_PROB_HIGH_SCALE = 10
NON_HKD_PROB_HIGH_CAP = 95

NON_HKD_PROB_MEDIUM_BASE = 75
NON_HKD_PROB_MEDIUM_SCALE = 25

NON_HKD_PROB_LOW_BASE = 45
NON_HKD_PROB_LOW_SCALE = 15

NON_HKD_PROB_VLOW_BASE = 15
NON_HKD_PROB_VLOW_SCALE = 5


def compute_feasibility(
    actual_gap: float,
    days_remaining: int,
    monthly_avg: float,
    unit: str = "HKD",
) -> dict:
    """Assess whether an already netted gap is achievable within its deadline."""
    if actual_gap <= 0:
        return {
            "level": "achieved",
            "level_label": "Achieved",
            "probability_pct": 100,
            "daily_needed": 0,
            "narrative": (
                "The target is already achieved or fully covered by pending premium."
            ),
        }

    daily_avg = (
        monthly_avg / DAYS_PER_MONTH_APPROX
        if monthly_avg > 0
        else 0
    )
    daily_needed = (
        round(actual_gap / days_remaining)
        if days_remaining > 0
        else float("inf")
    )

    if unit == "HKD":
        required_ratio = (
            daily_needed / daily_avg
            if daily_avg > 0
            else float("inf")
        )
        if required_ratio == float("inf"):
            level = "very_low"
            probability_pct = FEASIBILITY_PROB_FLOOR
        elif required_ratio <= FEASIBILITY_RATIO_HIGH:
            level = "high"
            probability_pct = min(
                round(
                    FEASIBILITY_PROB_HIGH_BASE
                    - required_ratio * FEASIBILITY_PROB_HIGH_SCALE
                ),
                FEASIBILITY_PROB_HIGH_CAP,
            )
        elif required_ratio <= FEASIBILITY_RATIO_MEDIUM:
            level = "medium"
            probability_pct = round(
                FEASIBILITY_PROB_MEDIUM_BASE
                - (required_ratio - FEASIBILITY_RATIO_HIGH)
                * FEASIBILITY_PROB_MEDIUM_SCALE
            )
        elif required_ratio <= FEASIBILITY_RATIO_LOW:
            level = "low"
            probability_pct = round(
                FEASIBILITY_PROB_LOW_BASE
                - (required_ratio - FEASIBILITY_RATIO_MEDIUM)
                * FEASIBILITY_PROB_LOW_SCALE
            )
        else:
            level = "very_low"
            probability_pct = max(
                round(
                    FEASIBILITY_PROB_VLOW_BASE
                    - (required_ratio - FEASIBILITY_RATIO_LOW)
                    * FEASIBILITY_PROB_VLOW_SCALE
                ),
                FEASIBILITY_PROB_FLOOR,
            )

        narrative = (
            f"{days_remaining} days remain for an actual gap of {actual_gap:,} {unit}. "
            f"Monthly average is {monthly_avg:,}; {daily_needed:,} per day is needed "
            f"({required_ratio:.2f}x the current daily average)."
        )
    else:
        weeks_remaining = max(days_remaining / 7, 0.5)
        per_week_needed = actual_gap / weeks_remaining
        required_ratio = (
            per_week_needed / NON_HKD_WEEKLY_BASELINE
            if per_week_needed > 0
            else 0
        )

        if required_ratio <= NON_HKD_RATIO_HIGH:
            level = "high"
            probability_pct = min(
                round(
                    NON_HKD_PROB_HIGH_BASE
                    - required_ratio * NON_HKD_PROB_HIGH_SCALE
                ),
                NON_HKD_PROB_HIGH_CAP,
            )
        elif required_ratio <= NON_HKD_RATIO_MEDIUM:
            level = "medium"
            probability_pct = round(
                NON_HKD_PROB_MEDIUM_BASE
                - (required_ratio - NON_HKD_RATIO_HIGH)
                * NON_HKD_PROB_MEDIUM_SCALE
            )
        elif required_ratio <= NON_HKD_RATIO_LOW:
            level = "low"
            probability_pct = round(
                NON_HKD_PROB_LOW_BASE
                - (required_ratio - NON_HKD_RATIO_MEDIUM)
                * NON_HKD_PROB_LOW_SCALE
            )
        else:
            level = "very_low"
            probability_pct = max(
                round(
                    NON_HKD_PROB_VLOW_BASE
                    - (required_ratio - NON_HKD_RATIO_LOW)
                    * NON_HKD_PROB_VLOW_SCALE
                ),
                FEASIBILITY_PROB_FLOOR,
            )

        narrative = (
            f"{days_remaining} days (about {weeks_remaining:.1f} weeks) remain for an "
            f"actual gap of {actual_gap:,} {unit}; {per_week_needed:.1f} {unit} per "
            "week is required."
        )

    level_labels = {
        "high": "High feasibility",
        "medium": "Medium feasibility",
        "low": "Low feasibility",
        "very_low": "Very low feasibility",
    }
    return {
        "level": level,
        "level_label": level_labels[level],
        "probability_pct": max(probability_pct, FEASIBILITY_PROB_FLOOR),
        "daily_needed": daily_needed,
        "required_ratio": round(required_ratio, 2),
        "narrative": narrative,
    }
