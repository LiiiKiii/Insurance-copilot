"""Pure attribution-gap calculation used by planning advice.

This module intentionally exposes only the calculation contract required by
``GenerateImprovementAdviceTool``.  It is not registered as an agent tool, so
adding it does not change the chat agent's available tools or selection logic.
"""

from __future__ import annotations

from typing import Any


_SIGNIFICANT_GAP_PCT = 5
_MEDIUM_IMPACT_PCT = 10
_HIGH_IMPACT_PCT = 20
_LOWER_IS_BETTER = {
    "new_lead_response_hours",
    "response_time",
    "complaint_rate",
}
_NON_DIMENSION_KEYS = {
    "agent_id",
    "period",
    "key_metrics",
    "peer_comparison",
}


def _impact(gap_pct: float) -> str:
    magnitude = abs(gap_pct)
    if magnitude >= _HIGH_IMPACT_PCT:
        return "高"
    if magnitude >= _MEDIUM_IMPACT_PCT:
        return "中"
    return "低"


def _is_number(value: Any) -> bool:
    """Return whether value is a usable numeric metric (excluding booleans)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _gap_item(
    *,
    dimension: str,
    metric: str,
    label: str,
    value: int | float,
    peer_avg: int | float,
    unit: str = "",
    lower_is_better: bool = False,
) -> dict[str, Any] | None:
    if peer_avg == 0:
        return None

    gap_pct = round((value - peer_avg) / abs(peer_avg) * 100, 1)
    if abs(gap_pct) < _SIGNIFICANT_GAP_PCT:
        return None

    is_weakness = (
        gap_pct > _SIGNIFICANT_GAP_PCT
        if lower_is_better
        else gap_pct < -_SIGNIFICANT_GAP_PCT
    )
    return {
        "dimension": dimension,
        "metric": metric,
        "label": label,
        "value": value,
        "peer_avg": peer_avg,
        "gap_pct": gap_pct,
        "unit": unit,
        "is_weakness": is_weakness,
        "impact": _impact(gap_pct),
    }


def compute_attribution_gap(dimensions: dict[str, Any]) -> list[dict[str, Any]]:
    """Compare attribution metrics with peer averages.

    The calculation accepts all attribution snapshots currently used by the
    project: ``key_metrics.dimensions``, paired ``data``/``peer_avg`` maps,
    and nested ``metrics`` maps.  Non-numeric values and zero peer averages
    are ignored because they cannot produce a meaningful percentage gap.
    """
    if not isinstance(dimensions, dict):
        return []

    results: list[dict[str, Any]] = []
    key_metrics = dimensions.get("key_metrics")
    if isinstance(key_metrics, dict):
        metric_dimensions = key_metrics.get("dimensions", [])
        if isinstance(metric_dimensions, list):
            for metric_data in metric_dimensions:
                if not isinstance(metric_data, dict):
                    continue
                value = metric_data.get("current")
                peer_avg = metric_data.get("peer_avg")
                if not _is_number(value) or not _is_number(peer_avg):
                    continue
                name = metric_data.get("name") or metric_data.get("name_en", "")
                item = _gap_item(
                    dimension="key_metrics",
                    metric=str(name),
                    label=str(name),
                    value=value,
                    peer_avg=peer_avg,
                    unit=str(metric_data.get("unit", "")),
                )
                if item is not None:
                    results.append(item)

    for dimension, dimension_data in dimensions.items():
        if dimension in _NON_DIMENSION_KEYS or not isinstance(dimension_data, dict):
            continue

        dimension_label = str(dimension_data.get("label", dimension))
        data = dimension_data.get("data")
        peer_averages = dimension_data.get("peer_avg")
        if isinstance(data, dict) and isinstance(peer_averages, dict) and data and peer_averages:
            for metric, value in data.items():
                peer_avg = peer_averages.get(metric)
                if not _is_number(value) or not _is_number(peer_avg):
                    continue
                item = _gap_item(
                    dimension=dimension,
                    metric=metric,
                    label=f"{dimension_label} — {metric}",
                    value=value,
                    peer_avg=peer_avg,
                    lower_is_better=metric in _LOWER_IS_BETTER,
                )
                if item is not None:
                    results.append(item)
            continue

        metrics = dimension_data.get("metrics")
        if not isinstance(metrics, dict):
            continue
        for metric, metric_data in metrics.items():
            if not isinstance(metric_data, dict):
                continue
            value = metric_data.get("value")
            if value is None:
                value = metric_data.get("current")
            peer_avg = metric_data.get("peer_avg")
            if peer_avg is None:
                peer_avg = metric_data.get("peer_average")
            if not _is_number(value) or not _is_number(peer_avg):
                continue
            item = _gap_item(
                dimension=dimension,
                metric=metric,
                label=str(metric_data.get("label") or f"{dimension_label} — {metric}"),
                value=value,
                peer_avg=peer_avg,
                unit=str(metric_data.get("unit", "")),
            )
            if item is not None:
                results.append(item)

    results.sort(
        key=lambda item: (
            0 if item["is_weakness"] else 1,
            item["gap_pct"],
        )
    )
    return results
