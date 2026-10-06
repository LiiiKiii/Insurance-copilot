"""Retrieve an agent's submitted and pending policies from the database."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from admin.db import get_sync_db
from admin.models.agent_data import AgentClient, AgentPerformanceMetrics, AgentPolicy
from nanobot.agent.tools.base import Tool

from ._db import db_error


class GetPendingPoliciesTool(Tool):
    """Return policy records and related client details without reasoning."""

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "get_pending_policies"

    @property
    def description(self) -> str:
        return (
            "[Data Layer] Retrieve an agent's submitted policies, including "
            "client, product, premium, underwriting status, submission date, "
            "and linked client tags. Return every matching policy."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Agent ID, for example AGT001",
                },
            },
            "required": ["agent_id"],
        }

    async def execute(self, **kwargs: Any) -> str:
        agent_id = kwargs["agent_id"]

        try:
            with get_sync_db() as db:
                policies = (
                    db.query(AgentPolicy)
                    .filter(AgentPolicy.agent_id == agent_id)
                    .order_by(AgentPolicy.submit_date.desc())
                    .all()
                )
                performance = (
                    db.query(AgentPerformanceMetrics.pending_premium_current)
                    .filter(AgentPerformanceMetrics.agent_id == agent_id)
                    .order_by(AgentPerformanceMetrics.period_end.desc())
                    .first()
                )
                clients = (
                    db.query(AgentClient)
                    .filter(AgentClient.agent_id == agent_id)
                    .all()
                )
        except Exception as exc:
            return db_error(exc)

        client_map = {
            client.client_id: {
                "name": client.name,
                "age": client.age,
                "premium": client.premium,
                "tag_categories": client.tag_categories,
                "tag_labels": client.tag_labels,
            }
            for client in clients
        }

        policy_items: list[dict[str, Any]] = []
        for policy in policies:
            client = client_map.get(policy.customer_id) if policy.customer_id else None
            item: dict[str, Any] = {
                "policy_id": policy.policy_id,
                "client_name": policy.client_name,
                "premium": policy.premium,
                "product": policy.product,
                "status": policy.status,
                "status_detail": policy.status_detail,
                "customer_id": policy.customer_id,
                "submit_date": policy.submit_date,
                "estimated_approval_days_min": policy.est_days_min,
                "estimated_approval_days_max": policy.est_days_max,
            }
            if client is not None:
                item.update(
                    client_age=client["age"],
                    client_tag_categories=client["tag_categories"],
                    client_tag_labels=client["tag_labels"],
                )
            policy_items.append(item)

        calculated_pending = sum(item["premium"] or 0 for item in policy_items)
        stored_pending = performance.pending_premium_current if performance else None

        return json.dumps(
            {
                "agent_id": agent_id,
                "total_count": len(policy_items),
                "total_pending_premium": (
                    stored_pending if stored_pending is not None else calculated_pending
                ),
                "policies": policy_items,
            },
            indent=2,
        )
