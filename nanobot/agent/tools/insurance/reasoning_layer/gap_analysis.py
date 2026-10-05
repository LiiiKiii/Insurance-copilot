"""Deterministic competition-gap analysis for the A2 reasoning layer."""


PARTIAL_COVERAGE_THRESHOLD = 0.5


def compute_gap_analysis(
    competitions: list[dict],
    pending_premium: float,
) -> list[dict]:
    """Allocate one shared pending-premium pool across competition gaps.

    Pending premium is allocated to positive HKD gaps in ascending
    ``days_remaining`` order. Results retain the caller's original order.
    """
    remaining_pool = float(pending_premium or 0)
    results: list[dict] = []

    for competition in competitions:
        gap = competition.get("gap")
        unit = competition.get("unit", "HKD")
        result = {
            "competition_id": competition.get("id"),
            "competition_name": competition.get("name"),
            "nominal_gap": gap,
            "unit": unit,
            "deadline": competition.get("deadline"),
            "days_remaining": competition.get("days_remaining"),
            "tags": competition.get("tags", []),
            "actual_gap": 0,
            "pending_deduction": 0,
            "pending_coverage_pct": 0.0,
            "status": "open",
        }

        if gap is None or gap <= 0:
            result.update(
                actual_gap=0,
                pending_deduction=0,
                pending_coverage_pct=100.0,
                status="achieved",
            )
        elif unit != "HKD":
            result.update(
                actual_gap=gap,
                pending_deduction=0,
                pending_coverage_pct=0.0,
                status="open",
            )

        results.append(result)

    priority_indexes = sorted(
        range(len(competitions)),
        key=lambda index: (
            competitions[index].get("days_remaining") is None,
            competitions[index].get("days_remaining"),
        ),
    )

    for index in priority_indexes:
        competition = competitions[index]
        gap = competition.get("gap")
        unit = competition.get("unit", "HKD")

        if gap is None or gap <= 0 or unit != "HKD":
            continue

        deduction = min(gap, remaining_pool) if remaining_pool > 0 else 0
        remaining_pool -= deduction
        actual_gap = max(gap - deduction, 0)
        coverage_fraction = deduction / gap
        coverage_pct = round(coverage_fraction * 100, 1)

        if actual_gap == 0:
            status = "covered_by_pending"
            note = "Pending premium fully covers the nominal gap."
        elif coverage_fraction >= PARTIAL_COVERAGE_THRESHOLD:
            status = "partially_covered"
            note = f"Pending premium covers {coverage_pct}% of the nominal gap."
        elif deduction > 0:
            status = "needs_new_business"
            note = f"Pending premium covers {coverage_pct}% of the nominal gap."
        else:
            status = "open"
            note = "No pending premium is available to reduce the nominal gap."

        results[index].update(
            actual_gap=actual_gap,
            pending_deduction=deduction,
            pending_coverage_pct=coverage_pct,
            status=status,
            note=note,
        )

    return results
