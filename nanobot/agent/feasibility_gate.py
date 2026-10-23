"""M1 server-owned feasibility decision for authenticated insurance chat."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from nanobot.agent.tools.insurance.reasoning_layer.feasibility import compute_feasibility
from nanobot.agent.tools.registry import ToolRegistry


@dataclass(frozen=True)
class FeasibilityDecision:
    content: str
    status: str
    reason: str
    target_id: str | None
    tool_events: tuple[dict[str, str], ...]


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _target(question: str, rows: list[Any]) -> dict[str, Any] | None:
    text = question.casefold()
    written_premium = "written premium" in text or "protection premium" in text or "书面保费" in question or "書面保費" in question
    acronyms = set(re.findall(r"\b(?:MDRT|COT|TTT|IDA)\b", question, re.IGNORECASE))
    matches = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        named = any(isinstance(row.get(key), str) and len(row[key]) >= 4
                    and row[key].casefold() in text for key in ("id", "name", "name_en"))
        names = " ".join(str(row.get(key) or "") for key in ("id", "name", "name_en"))
        named = named or any(re.search(rf"\b{acronym}\b", names, re.IGNORECASE)
                             for acronym in acronyms)
        premium = written_premium and row.get("target_metric") == "protection_premium"
        if named or premium:
            matches.append(row)
    return matches[0] if len(matches) == 1 else None


def _amount(value: int | float) -> str:
    return f"{value:,.2f}".rstrip("0").rstrip(".")


async def assess_authenticated_feasibility(
    question: str, agent_id: str, registry: ToolRegistry,
) -> FeasibilityDecision:
    """Use only agent-bound data Tools and validated deterministic Tool results."""
    events: list[dict[str, str]] = []
    target_id: str | None = None

    def unavailable(reason: str, explanation: str) -> FeasibilityDecision:
        return FeasibilityDecision(
            content=f"Feasibility assessment unavailable: {explanation}",
            status="unavailable", reason=reason, target_id=target_id,
            tool_events=tuple(events),
        )

    async def invoke(name: str, args: dict[str, Any]) -> dict[str, Any] | None:
        raw, status = await registry.execute_with_status(name, args)
        events.append({"name": name, "status": status})
        if status != "completed":
            return None
        try:
            result = json.loads(raw)
        except (TypeError, ValueError):
            return None
        return result if isinstance(result, dict) and "error" not in result else None

    competitions = await invoke("get_competition_status", {"agent_id": agent_id})
    if competitions is None or competitions.get("agent_id") != agent_id or not isinstance(competitions.get("competitions"), list):
        return unavailable("competition_data", "authorized competition data is missing or invalid.")
    selected = _target(question, competitions["competitions"])
    if selected is None:
        return unavailable("target", "one specific target could not be identified; name the competition or written premium target.")
    target_id = selected.get("id") if isinstance(selected.get("id"), str) else None
    if not target_id:
        return unavailable("target", "the target identifier is missing.")
    if re.search(r"\bHKD\b", question, re.IGNORECASE) or "港币" in question or "港幣" in question:
        return unavailable("unit", "the requested HKD target has no matching USD premium baseline.")
    if (re.search(r"\bpolicy[- ]count\s+(?:target|goal)\b", question, re.IGNORECASE)
            or "保单数目标" in question or "保單數目標" in question):
        return unavailable("unit", "a policy-count target cannot use the USD premium baseline.")
    if selected.get("target_metric") != "protection_premium" or selected.get("unit") != "USD":
        return unavailable("unit", "a matching USD written-premium baseline is unavailable for this target.")
    current, target, gap = (selected.get(key) for key in ("current_value", "target_value", "gap"))
    days, deadline = selected.get("days_remaining"), selected.get("deadline")
    if (not all(_number(value) for value in (current, target, gap))
            or current < 0 or target <= 0 or gap < 0
            or abs(gap - max(target - current, 0)) > 0.01
            or isinstance(days, bool) or not isinstance(days, int)
            or not isinstance(deadline, str)):
        return unavailable("target_values", "the target's current value, gap, or deadline is missing or inconsistent.")
    try:
        due = date.fromisoformat(deadline)
    except ValueError:
        return unavailable("deadline", "the target deadline is invalid.")
    if days != (due - date.today()).days or days <= 0:
        return unavailable("deadline", "the target deadline is missing or has passed.")

    snapshot = await invoke("get_performance_snapshot", {
        "agent_id": agent_id, "metrics": ["protection_premium"],
    })
    metric = snapshot.get("metrics", {}).get("protection_premium") if isinstance(snapshot, dict) and isinstance(snapshot.get("metrics"), dict) else None
    if (not isinstance(snapshot, dict) or snapshot.get("agent_id") != agent_id
            or not isinstance(metric, dict) or metric.get("unit") != "USD"
            or not _number(metric.get("current"))
            or abs(metric["current"] - current) > 0.01):
        return unavailable("baseline", "a matching, agent-owned USD premium snapshot is missing.")
    period = snapshot.get("period")
    try:
        start_text, end_text = period.split(" to ")
        start, end = date.fromisoformat(start_text), date.fromisoformat(end_text)
    except (AttributeError, ValueError):
        return unavailable("period", "the premium snapshot period is missing or invalid.")
    if start > end or end > date.today():
        return unavailable("period", "the premium snapshot period is inconsistent.")

    pace = await invoke("calculate_run_rate", {
        "current": current, "target": target,
        "period_start": start.isoformat(), "as_of_date": end.isoformat(),
    })
    monthly_avg = pace.get("monthly_avg") if isinstance(pace, dict) else None
    if (not isinstance(pace, dict) or not _number(monthly_avg) or monthly_avg < 0
            or pace.get("current") != current or pace.get("target") != target):
        return unavailable("pace", "a validated USD monthly premium baseline is unavailable.")

    assessment = await invoke("assess_gap_feasibility", {
        "actual_gap": gap, "days_remaining": days,
        "monthly_avg": monthly_avg, "unit": "USD",
    })
    if not isinstance(assessment, dict):
        return unavailable("assessment", "the deterministic feasibility calculation did not complete.")
    try:
        reference = compute_feasibility(gap, days, monthly_avg, "USD")
    except (ValueError, OverflowError):
        return unavailable("assessment_result", "the deterministic feasibility result is invalid.")
    level, probability = assessment.get("level"), assessment.get("probability_pct")
    if (level != reference["level"] or probability != reference["probability_pct"]
            or isinstance(probability, bool) or not isinstance(probability, int)):
        return unavailable("assessment_result", "the deterministic feasibility result is invalid.")

    label = reference.get("level_label", level).lower()
    conclusion = (
        f"{selected.get('name_en') or selected.get('name') or target_id}: recorded "
        f"USD {_amount(current)} of USD {_amount(target)}, with a nominal open gap of "
        f"USD {_amount(gap)} and {days} days to the deadline. "
        f"Estimated feasibility is {label} ({probability}%) based on the "
        f"USD premium snapshot through {end.isoformat()}. "
        "Time remaining shows mathematical opportunity; estimated feasibility is "
        "a separate assessment and does not guarantee the target will be reached. "
        "This estimate does not treat pending premium as issued business."
    )
    return FeasibilityDecision(
        content=conclusion, status="completed", reason="assessed",
        target_id=target_id, tool_events=tuple(events),
    )
