"""Tenant-scoped competition and entry administration endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select

from admin.dependencies import DB, RoleAdmin, RoleAny, _error
from admin.models.competition import Competition, CompetitionEntry
from admin.routers._business import (
    commit_or_error,
    ensure_tenant_access,
    ensure_tenant_exists,
    resolve_tenant_id,
)

router = APIRouter(prefix="/api/admin/competitions", tags=["admin-competitions"])
DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"


class CompetitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str | None = Field(default=None, max_length=36)
    name: str = Field(min_length=1, max_length=100)
    name_en: str = Field(default="", max_length=100)
    type: str = Field(default="competition", min_length=1, max_length=30)
    target_metric: str = Field(min_length=1, max_length=50)
    target_value: float | None = Field(default=None, ge=0)
    unit: str = Field(default="USD", max_length=20)
    deadline: str = Field(pattern=DATE_PATTERN)
    reward: str = ""
    description: str = ""
    is_active: bool = True


class CompetitionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    name_en: str | None = Field(default=None, max_length=100)
    type: str | None = Field(default=None, min_length=1, max_length=30)
    target_metric: str | None = Field(default=None, min_length=1, max_length=50)
    target_value: float | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=20)
    deadline: str | None = Field(default=None, pattern=DATE_PATTERN)
    reward: str | None = None
    description: str | None = None
    is_active: bool | None = None


class EntryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    competition_id: str = Field(min_length=1, max_length=36)
    agent_id: str = Field(min_length=1, max_length=20)
    current_value: float | None = None
    gap: float | None = None
    status: str = Field(default="", max_length=20)


class EntryUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_value: float | None = None
    gap: float | None = None
    status: str | None = Field(default=None, max_length=20)


def _competition_payload(row: Competition) -> dict[str, Any]:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "name": row.name,
        "name_en": row.name_en,
        "type": row.type,
        "target_metric": row.target_metric,
        "target_value": row.target_value,
        "unit": row.unit,
        "deadline": row.deadline,
        "reward": row.reward,
        "description": row.description,
        "is_active": row.is_active,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _entry_payload(row: CompetitionEntry) -> dict[str, Any]:
    return {
        "id": row.id,
        "competition_id": row.competition_id,
        "agent_id": row.agent_id,
        "current_value": row.current_value,
        "gap": row.gap,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def _load_competition(competition_id: str, db: DB) -> Competition:
    competition = await db.get(Competition, competition_id)
    if competition is None:
        raise _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Competition not found")
    return competition


async def _load_entry(
    entry_id: str,
    db: DB,
) -> tuple[CompetitionEntry, Competition]:
    entry = await db.get(CompetitionEntry, entry_id)
    if entry is None:
        raise _error(
            status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Competition entry not found"
        )
    competition = await _load_competition(entry.competition_id, db)
    return entry, competition


@router.get("/")
async def list_competitions(
    current_user: RoleAny,
    db: DB,
    tenant_id: str | None = None,
    is_active: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    if not current_user.is_superadmin and tenant_id not in (
        None,
        current_user.tenant_id,
    ):
        raise _error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "Access denied")

    statement = select(Competition)
    if tenant_id is not None:
        statement = statement.where(Competition.tenant_id == tenant_id)
    elif not current_user.is_superadmin:
        statement = statement.where(Competition.tenant_id == current_user.tenant_id)
    if is_active is not None:
        statement = statement.where(Competition.is_active == is_active)

    total = int(
        (
            await db.execute(
                select(func.count()).select_from(statement.order_by(None).subquery())
            )
        ).scalar_one()
    )
    rows = (
        (
            await db.execute(
                statement.order_by(Competition.deadline.asc(), Competition.id.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return {
        "ok": True,
        "data": [_competition_payload(row) for row in rows],
        "meta": {"total": total, "page": page, "page_size": page_size},
    }


@router.post("/")
async def create_competition(
    body: CompetitionRequest,
    current_user: RoleAdmin,
    db: DB,
) -> dict[str, Any]:
    tenant_id = resolve_tenant_id(current_user, body.tenant_id)
    await ensure_tenant_exists(db, tenant_id)
    competition = Competition(
        **body.model_dump(exclude={"tenant_id"}),
        tenant_id=tenant_id,
    )
    db.add(competition)
    await commit_or_error(
        db, conflict_message="Competition conflicts with existing data"
    )
    return {"ok": True, "data": _competition_payload(competition)}


@router.post("/entries")
async def create_entry(
    body: EntryRequest,
    current_user: RoleAdmin,
    db: DB,
) -> dict[str, Any]:
    competition = await _load_competition(body.competition_id, db)
    ensure_tenant_access(current_user, competition.tenant_id)
    duplicate = await db.execute(
        select(CompetitionEntry.id).where(
            CompetitionEntry.competition_id == body.competition_id,
            CompetitionEntry.agent_id == body.agent_id,
        )
    )
    if duplicate.first() is not None:
        raise _error(
            status.HTTP_409_CONFLICT,
            "DUPLICATE",
            "Agent is already entered in this competition",
        )
    entry = CompetitionEntry(**body.model_dump())
    db.add(entry)
    await commit_or_error(
        db, conflict_message="Competition entry conflicts with existing data"
    )
    return {"ok": True, "data": _entry_payload(entry)}


@router.get("/{competition_id}")
async def get_competition(
    competition_id: str,
    current_user: RoleAny,
    db: DB,
) -> dict[str, Any]:
    competition = await _load_competition(competition_id, db)
    ensure_tenant_access(current_user, competition.tenant_id)
    return {"ok": True, "data": _competition_payload(competition)}


@router.put("/{competition_id}")
async def update_competition(
    competition_id: str,
    body: CompetitionUpdateRequest,
    current_user: RoleAdmin,
    db: DB,
) -> dict[str, Any]:
    competition = await _load_competition(competition_id, db)
    ensure_tenant_access(current_user, competition.tenant_id)
    changes = body.model_dump(exclude_unset=True)
    required_fields = {"name", "type", "target_metric", "unit", "deadline"}
    if any(changes.get(field) is None for field in required_fields & changes.keys()):
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "INVALID_COMPETITION",
            "Required competition fields cannot be null",
        )
    for field, value in changes.items():
        setattr(competition, field, value)
    await commit_or_error(
        db, conflict_message="Competition conflicts with existing data"
    )
    return {"ok": True, "data": _competition_payload(competition)}


@router.delete("/{competition_id}")
async def delete_competition(
    competition_id: str,
    current_user: RoleAdmin,
    db: DB,
) -> dict[str, Any]:
    competition = await _load_competition(competition_id, db)
    ensure_tenant_access(current_user, competition.tenant_id)
    await db.execute(
        delete(CompetitionEntry).where(
            CompetitionEntry.competition_id == competition_id
        )
    )
    await db.delete(competition)
    await commit_or_error(
        db, conflict_message="Competition is still referenced by other records"
    )
    return {"ok": True, "data": {"message": "Competition deleted"}}


@router.get("/{competition_id}/entries")
async def list_entries(
    competition_id: str,
    current_user: RoleAny,
    db: DB,
) -> dict[str, Any]:
    competition = await _load_competition(competition_id, db)
    ensure_tenant_access(current_user, competition.tenant_id)
    rows = (
        (
            await db.execute(
                select(CompetitionEntry)
                .where(CompetitionEntry.competition_id == competition_id)
                .order_by(CompetitionEntry.agent_id.asc(), CompetitionEntry.id.asc())
            )
        )
        .scalars()
        .all()
    )
    return {"ok": True, "data": [_entry_payload(row) for row in rows]}


@router.put("/entries/{entry_id}")
async def update_entry(
    entry_id: str,
    body: EntryUpdateRequest,
    current_user: RoleAdmin,
    db: DB,
) -> dict[str, Any]:
    entry, competition = await _load_entry(entry_id, db)
    ensure_tenant_access(current_user, competition.tenant_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    await commit_or_error(
        db, conflict_message="Competition entry conflicts with existing data"
    )
    return {"ok": True, "data": _entry_payload(entry)}


@router.delete("/entries/{entry_id}")
async def delete_entry(
    entry_id: str,
    current_user: RoleAdmin,
    db: DB,
) -> dict[str, Any]:
    entry, competition = await _load_entry(entry_id, db)
    ensure_tenant_access(current_user, competition.tenant_id)
    await db.delete(entry)
    await commit_or_error(db, conflict_message="Competition entry is still referenced")
    return {"ok": True, "data": {"message": "Competition entry deleted"}}
