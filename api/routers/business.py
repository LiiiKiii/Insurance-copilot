"""Authenticated compatibility reads consumed by the main agent UI."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from admin.dependencies import DB, CurrentUser, _error, is_admin_role
from admin.models.competition import Competition, CompetitionEntry
from admin.models.user import User
from api.services.competition_enrichment import enrich_competitions


router = APIRouter(tags=["business-compatibility"])


def _is_manager(user: User) -> bool:
    role_names = {
        role.name
        for role in user.roles
        if role.tenant_id == user.tenant_id
    }
    return (
        is_admin_role(user)
        or "agent_manager" in role_names
        or user.tier in {"director", "team_lead"}
    )


async def _accessible_agent(
    agent_id: str,
    current_user: User,
    db: DB,
) -> User | None:
    statement = select(User).where(User.username == agent_id, User.is_active.is_(True))
    if not current_user.is_superadmin:
        statement = statement.where(User.tenant_id == current_user.tenant_id)
    matches = list((await db.scalars(statement)).all())
    if len(matches) != 1:
        return None

    target = matches[0]
    if target.id == current_user.id or current_user.is_superadmin:
        return target
    if _is_manager(current_user) and (
        current_user.tier != "team_lead" or target.supervisor_id == current_user.id
    ):
        return target
    raise _error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "Agent access denied")


async def _competition_rows(agent: User, db: DB) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(Competition, CompetitionEntry)
            .join(
                CompetitionEntry,
                CompetitionEntry.competition_id == Competition.id,
            )
            .where(
                CompetitionEntry.agent_id == agent.username,
                Competition.tenant_id == agent.tenant_id,
                Competition.is_active.is_(True),
            )
            .order_by(Competition.deadline.asc(), Competition.id.asc())
        )
    ).all()

    payload: list[dict[str, Any]] = []
    for competition, entry in rows:
        target_value = (
            (entry.current_value or 0) + entry.gap
            if entry.current_value is not None and entry.gap is not None
            else competition.target_value
        )
        payload.append(
            {
                "id": competition.id,
                "name": competition.name,
                "name_en": competition.name_en,
                "type": competition.type,
                "target_metric": competition.target_metric,
                "target_value": target_value,
                "current_value": entry.current_value,
                "gap": entry.gap,
                "unit": competition.unit,
                "deadline": competition.deadline,
                "days_remaining": None,
                "tags": [],
                "status": entry.status or "",
                "reward": competition.reward,
                "description": competition.description,
            }
        )
    return payload


@router.get("/api/agent-info")
async def get_agent_info(
    current_user: CurrentUser,
    db: DB,
    agent_id: str = Query(..., min_length=1, max_length=100),
) -> dict[str, Any]:
    agent = await _accessible_agent(agent_id, current_user, db)
    if agent is None:
        return {"ok": False, "error": "Agent not found"}
    display_name = (agent.display_name or agent.username).split("(")[0].strip()
    return {
        "ok": True,
        "data": {
            "agent_id": agent.username,
            "name_zh": display_name,
            "name_en": "",
            "nickname": display_name,
            "rank": agent.tier or "agent",
            "rank_en": agent.tier or "agent",
            "title": agent.tier or "",
            "team": "",
            "region": "",
            "email": agent.email or "",
        },
    }


@router.get("/api/competitions")
async def get_competitions(
    current_user: CurrentUser,
    db: DB,
    agent_id: str = Query(..., min_length=1, max_length=100),
) -> dict[str, Any]:
    agent = await _accessible_agent(agent_id, current_user, db)
    if agent is None:
        return {
            "agent_id": agent_id,
            "query_date": date.today().isoformat(),
            "total_competitions": 0,
            "competitions": [],
        }
    competitions = enrich_competitions(await _competition_rows(agent, db))
    return {
        "agent_id": agent_id,
        "query_date": date.today().isoformat(),
        "total_competitions": len(competitions),
        "competitions": competitions,
    }


@router.get("/api/proactive-alerts")
async def get_proactive_alerts(
    current_user: CurrentUser,
    db: DB,
    agent_id: str = Query(..., min_length=1, max_length=100),
) -> dict[str, Any]:
    agent = await _accessible_agent(agent_id, current_user, db)
    if agent is None:
        return {"agent_id": agent_id, "agent_name": "", "alerts": []}

    agent_name = (agent.display_name or agent.username).split("(")[0].strip()
    competitions = enrich_competitions(await _competition_rows(agent, db))
    alerts: list[dict[str, Any]] = []
    for competition in competitions:
        days_remaining = competition.get("days_remaining")
        gap = competition.get("gap")
        if (
            isinstance(days_remaining, int)
            and 0 <= days_remaining <= 30
            and gap is not None
            and gap > 0
        ):
            unit = competition.get("unit") or "HKD"
            amount = f"HKD {gap:,}" if unit == "HKD" else f"{gap}{unit}"
            alerts.append(
                {
                    "competition_name": competition["name"],
                    "days_remaining": days_remaining,
                    "gap": gap,
                    "unit": unit,
                    "urgency": "urgent" if days_remaining <= 14 else "important",
                    "tags": competition.get("tags", []),
                    "message": (
                        f"{agent_name}，{competition['name']}還差{amount}，"
                        f"距截止僅剩 {days_remaining} 天！"
                    ),
                }
            )
    alerts.sort(key=lambda item: item["days_remaining"])
    return {"agent_id": agent_id, "agent_name": agent_name, "alerts": alerts}
