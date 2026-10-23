"""Authenticated compatibility API for the agent workbench."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from admin.dependencies import DB, CurrentUser, _error, is_admin_role
from admin.models.agent_data import AgentPerformanceMetrics, AgentProfile
from admin.models.assessment import AgentAssessment
from admin.models.competition import Competition, CompetitionEntry
from admin.models.performance_target import PerformanceTarget
from admin.models.user import User

router = APIRouter(prefix="/api", tags=["agent-workbench"])


class TargetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_value: float = Field(ge=0)


class EntryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_id: str = Field(min_length=1, max_length=100)
    competition_id: str = Field(min_length=1, max_length=36)


class EntryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_value: float = Field(ge=0)


async def _tenant_users(db: DB, tenant_id: str) -> list[User]:
    return (
        await db.execute(select(User).where(User.tenant_id == tenant_id))
    ).scalars().all()


async def _authorise_agent(
    db: DB, current_user: User, agent_id: str, *, require_manager: bool = False
) -> User:
    statement = select(User).where(User.username == agent_id)
    if not current_user.is_superadmin:
        statement = statement.where(User.tenant_id == current_user.tenant_id)
    matches = (await db.execute(statement)).scalars().all()
    if len(matches) != 1:
        raise _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Agent not found")
    target = matches[0]

    if current_user.is_superadmin or is_admin_role(current_user):
        return target
    if target.id == current_user.id and not require_manager:
        return target

    users = await _tenant_users(db, current_user.tenant_id)
    by_id = {user.id: user for user in users}
    supervisor_id = target.supervisor_id
    visited: set[str] = set()
    while supervisor_id and supervisor_id not in visited:
        if supervisor_id == current_user.id:
            return target
        visited.add(supervisor_id)
        supervisor = by_id.get(supervisor_id)
        supervisor_id = supervisor.supervisor_id if supervisor else None

    raise _error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "Agent access denied")


def _rank(tier: str | None) -> str:
    return {
        "director": "Director",
        "team_lead": "Team Lead",
        "senior_agent": "Senior Insurance Agent",
        "agent": "Insurance Agent",
    }.get(tier or "agent", "Insurance Agent")


def _metric(
    row: AgentPerformanceMetrics,
    *,
    label: str,
    unit: str,
    current: str,
    target: str | None = None,
    rate: str | None = None,
    peer_avg: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "label": label,
        "current": getattr(row, current, None),
        "target": getattr(row, target, None) if target else None,
        "rate": getattr(row, rate, None) if rate else None,
        "unit": unit,
    }
    if peer_avg:
        result["peer_avg"] = getattr(row, peer_avg, None)
    return result


def _performance_metrics(row: AgentPerformanceMetrics) -> dict[str, dict[str, Any]]:
    metrics = {
        "protection_premium": _metric(row, label="MDRT 年度累積 (MDRT Credit)", unit="Credit", current="protection_premium_current", target="protection_premium_target", rate="protection_premium_rate"),
        "pending_premium": _metric(row, label="待批保費 (Pending Premium)", unit="HKD", current="pending_premium_current"),
        "avg_case_size": _metric(row, label="件均保費 (Average Case Size)", unit="HKD", current="avg_case_size_current", target="avg_case_size_target", rate="avg_case_size_rate", peer_avg="avg_case_size_peer_avg"),
        "submission_count": _metric(row, label="遞交件數 (Submissions)", unit="件", current="submission_count_current", target="submission_count_target", rate="submission_count_rate"),
        "policy_count": _metric(row, label="保單件數 (Policy Count)", unit="件", current="policy_count"),
        "conversion_rate": _metric(row, label="入單轉化率 (Conversion Rate)", unit="%", current="conversion_rate_current", target="conversion_rate_target", rate="conversion_rate_rate", peer_avg="conversion_rate_peer_avg"),
        "new_clients": _metric(row, label="客戶新增數量 (New Clients)", unit="位", current="new_clients_current", target="new_clients_target", rate="new_clients_rate"),
        "client_retention": _metric(row, label="老客戶續保率 (Client Retention)", unit="%", current="client_retention_current", target="client_retention_target", rate="client_retention_rate"),
        "fyc": _metric(row, label="首年佣金 (FYC)", unit="HKD", current="ytd_fyc", target="fyc_target", rate="fyc_rate"),
        "quarter_fyc": _metric(row, label="季度總 FYC (Quarterly FYC)", unit="HKD", current="quarter_fyc"),
        "daily_fyc": _metric(row, label="日均 FYC (Daily Avg FYC)", unit="HKD", current="daily_fyc"),
        "total_clients": _metric(row, label="客戶總數 (Total Clients)", unit="位", current="total_clients"),
        "churn_rate": _metric(row, label="客戶流失率 (Churn Rate)", unit="%", current="churn_rate"),
        "churn_clients": _metric(row, label="流失客戶數 (Churn Clients)", unit="位", current="churn_clients"),
        "renewal_due_clients": _metric(row, label="應續保客戶 (Renewal Due)", unit="位", current="renewal_due_clients"),
        "ai_training_usage": _metric(row, label="AI陪練累計次數 (AI Training Count)", unit="次", current="ai_training_usage_current", target="ai_training_usage_target", rate="ai_training_usage_rate"),
        "ai_practice_rate": _metric(row, label="AI陪練完成度 (AI Practice Rate)", unit="%", current="ai_practice_rate"),
        "online_university": _metric(row, label="線上大學堂狀態", unit="", current="online_university"),
    }

    definitions = (row.metric_metadata or {}).get("metrics", {})
    for key, value in metrics.items():
        for field in ("label", "unit", "description"):
            if field in definitions.get(key, {}):
                value[field] = definitions[key][field]
    return metrics


def _days_remaining(deadline: str) -> int | None:
    try:
        return (datetime.strptime(deadline, "%Y-%m-%d").date() - date.today()).days
    except (TypeError, ValueError):
        return None


def _competition_payload(
    competition: Competition, entry: CompetitionEntry
) -> dict[str, Any]:
    current = entry.current_value
    gap = entry.gap
    target = current + gap if current is not None and gap is not None else competition.target_value
    days = _days_remaining(competition.deadline)
    if gap is not None and gap <= 0:
        feasibility = "Achieved"
    elif days is not None and days < 0:
        feasibility = "Very difficult"
    elif days is not None and days <= 30:
        feasibility = "Challenging"
    else:
        feasibility = "Achievable"
    urgency = "critical" if gap and days is not None and days <= 30 else "important" if gap and days is not None and days <= 90 else "normal"
    return {
        "id": competition.id,
        "entry_id": entry.id,
        "name": competition.name_en or competition.name,
        "type": competition.type,
        "target_metric": competition.target_metric,
        "target_value": target,
        "current_value": current,
        "gap": gap,
        "unit": competition.unit,
        "deadline": competition.deadline,
        "days_remaining": days,
        "tags": [competition.target_metric.replace("_", " ")],
        "status": entry.status,
        "feasibility_hint": feasibility,
        "urgency_level": urgency,
        "reward": competition.reward,
        "description": competition.description,
    }


async def _competition_rows(
    db: DB, agent_id: str, tenant_id: str, *, active_only: bool = True
):
    statement = (
        select(Competition, CompetitionEntry)
        .join(CompetitionEntry, CompetitionEntry.competition_id == Competition.id)
        .where(
            CompetitionEntry.agent_id == agent_id,
            Competition.tenant_id == tenant_id,
        )
        .order_by(Competition.deadline.asc(), Competition.id.asc())
    )
    if active_only:
        statement = statement.where(Competition.is_active.is_(True))
    return (await db.execute(statement)).all()


@router.get("/agent-info")
async def agent_info(agent_id: str, current_user: CurrentUser, db: DB) -> dict:
    user = await _authorise_agent(db, current_user, agent_id)
    profile = await db.get(AgentProfile, agent_id)
    name = (profile.name_en if profile else None) or user.display_name or user.username
    return {"ok": True, "data": {
        "agent_id": agent_id,
        "name_en": name,
        "name_zh": name,
        "nickname": name.split()[0] if name else agent_id,
        "rank": _rank(user.tier),
        "tier": user.tier or "agent",
        "team": profile.team if profile else None,
        "license_no": profile.license_no if profile else None,
    }}


@router.get("/performance")
async def performance(agent_id: str, current_user: CurrentUser, db: DB) -> dict:
    target_user = await _authorise_agent(db, current_user, agent_id)
    row = (
        await db.execute(
            select(AgentPerformanceMetrics)
            .where(AgentPerformanceMetrics.agent_id == agent_id)
            .order_by(AgentPerformanceMetrics.period_end.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Performance data not found")
    assessments = (
        await db.execute(
            select(AgentAssessment)
            .where(
                AgentAssessment.tenant_id == target_user.tenant_id,
                AgentAssessment.agent_id == agent_id,
            )
            .order_by(AgentAssessment.subject.asc())
        )
    ).scalars().all()
    return {
        "agent_id": agent_id,
        "period": f"{row.period_start} to {row.period_end}",
        "metrics": _performance_metrics(row),
        "data_origin": (row.metric_metadata or {}).get("data_origin", {}),
        "assessments": [
            {
                "subject": item.subject,
                "unit": item.unit,
                "target_value": item.target_value,
                "current_value": item.current_value,
                "status": item.status,
                "remark": item.remark,
            }
            for item in assessments
        ],
    }


@router.get("/competitions")
async def competitions(agent_id: str, current_user: CurrentUser, db: DB) -> dict:
    target_user = await _authorise_agent(db, current_user, agent_id)
    rows = await _competition_rows(db, agent_id, target_user.tenant_id)
    return {"ok": True, "agent_id": agent_id, "competitions": [_competition_payload(c, e) for c, e in rows]}


@router.get("/targets")
async def targets(agent_id: str, current_user: CurrentUser, db: DB) -> dict:
    target_user = await _authorise_agent(db, current_user, agent_id)
    rows = (
        await db.execute(
            select(PerformanceTarget)
            .where(
                PerformanceTarget.tenant_id == target_user.tenant_id,
                PerformanceTarget.agent_id == agent_id,
            )
            .order_by(PerformanceTarget.metric_key.asc(), PerformanceTarget.period_end.desc(), PerformanceTarget.period_start.desc())
        )
    ).scalars().all()
    return {"ok": True, "data": [
        {
            "id": row.id,
            "agent_id": row.agent_id,
            "metric_key": row.metric_key,
            "metric_label": row.metric_label,
            "target_value": row.target_value,
            "unit": row.unit,
            "period_type": row.period_type,
            "period_start": row.period_start,
            "period_end": row.period_end,
        }
        for row in rows
    ]}


@router.put("/targets/{target_id}")
async def update_target(target_id: str, body: TargetUpdate, current_user: CurrentUser, db: DB) -> dict:
    target = await db.get(PerformanceTarget, target_id)
    if target is None:
        raise _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Target not found")
    await _authorise_agent(db, current_user, target.agent_id, require_manager=target.agent_id != current_user.username)
    target.target_value = body.target_value
    await db.commit()
    return {"ok": True, "data": {"id": target.id, "target_value": target.target_value}}


@router.get("/proactive-alerts")
async def proactive_alerts(agent_id: str, current_user: CurrentUser, db: DB) -> dict:
    target_user = await _authorise_agent(db, current_user, agent_id)
    rows = await _competition_rows(db, agent_id, target_user.tenant_id)
    alerts = []
    for competition, entry in rows:
        item = _competition_payload(competition, entry)
        if not item["gap"] or item["gap"] <= 0 or item["days_remaining"] is None or item["days_remaining"] < 0:
            continue
        alerts.append({
            "competition_name": item["name"],
            "days_remaining": item["days_remaining"],
            "gap": item["gap"],
            "unit": item["unit"],
            "message": f"{item['gap']:,.0f} {item['unit']} remaining with {item['days_remaining']} days left.",
            "urgency": "urgent" if item["days_remaining"] <= 30 else "important",
        })
    alerts.sort(key=lambda item: (item["days_remaining"], -item["gap"]))
    return {"ok": True, "alerts": alerts}


@router.get("/my-team")
async def my_team(agent_id: str, current_user: CurrentUser, db: DB) -> dict:
    manager = await _authorise_agent(db, current_user, agent_id)
    direct = (
        await db.execute(
            select(User)
            .where(User.tenant_id == manager.tenant_id, User.supervisor_id == manager.id, User.is_active.is_(True))
            .order_by(User.username.asc())
        )
    ).scalars().all()
    profiles = {
        row.agent_id: row
        for row in (
            await db.execute(select(AgentProfile).where(AgentProfile.agent_id.in_([user.username for user in direct])))
        ).scalars().all()
    } if direct else {}
    counts = dict(
        (
            await db.execute(
                select(User.supervisor_id, func.count(User.id))
                .where(User.tenant_id == manager.tenant_id, User.supervisor_id.in_([user.id for user in direct]))
                .group_by(User.supervisor_id)
            )
        ).all()
    ) if direct else {}
    return {"ok": True, "data": {"agent_id": agent_id, "team": [
        {
            "agent_id": user.username,
            "name_en": (profiles.get(user.username).name_en if profiles.get(user.username) else None) or user.display_name or user.username,
            "name_zh": (profiles.get(user.username).name_en if profiles.get(user.username) else None) or user.display_name or user.username,
            "nickname": ((profiles.get(user.username).name_en if profiles.get(user.username) else None) or user.display_name or user.username).split()[0],
            "tier": user.tier or "agent",
            "rank": _rank(user.tier),
            "sub_count": int(counts.get(user.id, 0)),
        }
        for user in direct
    ]}}


@router.get("/all-competitions")
async def all_competitions(current_user: CurrentUser, db: DB) -> dict:
    statement = select(Competition).where(Competition.is_active.is_(True))
    if not current_user.is_superadmin:
        statement = statement.where(Competition.tenant_id == current_user.tenant_id)
    rows = (await db.execute(statement.order_by(Competition.deadline.asc()))).scalars().all()
    return {"ok": True, "data": [
        {"id": row.id, "name": row.name_en or row.name, "type": row.type, "target_metric": row.target_metric, "target_value": row.target_value, "unit": row.unit, "deadline": row.deadline}
        for row in rows
    ]}


@router.get("/agent-competitions")
async def agent_competitions(agent_id: str, current_user: CurrentUser, db: DB) -> dict:
    target_user = await _authorise_agent(db, current_user, agent_id)
    rows = await _competition_rows(
        db, agent_id, target_user.tenant_id, active_only=False
    )
    return {"ok": True, "data": [
        {
            "entry_id": entry.id,
            "competition_id": competition.id,
            "competition_name": competition.name_en or competition.name,
            "target_metric": competition.target_metric,
            "competition_target": competition.target_value,
            "current_value": entry.current_value,
            "gap": entry.gap,
            "unit": competition.unit,
            "deadline": competition.deadline,
            "days_remaining": _days_remaining(competition.deadline),
            "status": entry.status,
        }
        for competition, entry in rows
    ]}


@router.post("/agent-competitions")
async def create_agent_competition(body: EntryCreate, current_user: CurrentUser, db: DB) -> dict:
    target_user = await _authorise_agent(
        db,
        current_user,
        body.agent_id,
        require_manager=body.agent_id != current_user.username,
    )
    competition = await db.get(Competition, body.competition_id)
    if competition is None or competition.tenant_id != target_user.tenant_id:
        raise _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Competition not found")
    existing = (
        await db.execute(select(CompetitionEntry).where(CompetitionEntry.competition_id == body.competition_id, CompetitionEntry.agent_id == body.agent_id))
    ).scalar_one_or_none()
    if existing is not None:
        return {"ok": True, "data": {"entry_id": existing.id}}
    entry = CompetitionEntry(competition_id=body.competition_id, agent_id=body.agent_id, current_value=0, gap=competition.target_value, status="active")
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return {"ok": True, "data": {"entry_id": entry.id}}


async def _load_entry_for_update(db: DB, current_user: User, entry_id: str) -> tuple[CompetitionEntry, Competition]:
    row = (
        await db.execute(
            select(CompetitionEntry, Competition)
            .join(Competition, Competition.id == CompetitionEntry.competition_id)
            .where(CompetitionEntry.id == entry_id)
        )
    ).one_or_none()
    if row is None:
        raise _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Competition entry not found")
    entry, competition = row
    target_user = await _authorise_agent(
        db,
        current_user,
        entry.agent_id,
        require_manager=entry.agent_id != current_user.username,
    )
    if competition.tenant_id != target_user.tenant_id:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "NOT_FOUND",
            "Competition entry not found",
        )
    return entry, competition


@router.put("/agent-competitions/{entry_id}")
async def update_agent_competition(entry_id: str, body: EntryUpdate, current_user: CurrentUser, db: DB) -> dict:
    entry, competition = await _load_entry_for_update(db, current_user, entry_id)
    entry.current_value = body.current_value
    entry.gap = max((competition.target_value or 0) - body.current_value, 0)
    entry.status = "completed" if entry.gap <= 0 else "active"
    await db.commit()
    return {"ok": True, "data": {"entry_id": entry.id, "current_value": entry.current_value, "gap": entry.gap}}


@router.delete("/agent-competitions/{entry_id}")
async def delete_agent_competition(entry_id: str, current_user: CurrentUser, db: DB) -> dict:
    entry, _ = await _load_entry_for_update(db, current_user, entry_id)
    await db.delete(entry)
    await db.commit()
    return {"ok": True, "data": {"entry_id": entry_id}}
