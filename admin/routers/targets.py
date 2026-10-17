"""Tenant-scoped performance target administration endpoints."""

from __future__ import annotations

from typing import Any, Self

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select

from admin.dependencies import DB, RoleAdmin, RoleAny, _error
from admin.models.performance_target import PerformanceTarget
from admin.routers._business import (
    commit_or_error,
    ensure_tenant_access,
    ensure_tenant_exists,
    resolve_tenant_id,
)

router = APIRouter(prefix="/api/admin/targets", tags=["admin-targets"])
DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"


class TargetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str | None = Field(default=None, max_length=36)
    agent_id: str = Field(min_length=1, max_length=20)
    metric_key: str = Field(min_length=1, max_length=50)
    metric_label: str = Field(default="", max_length=100)
    target_value: float = Field(ge=0)
    unit: str = Field(default="HKD", max_length=20)
    period_type: str = Field(default="annual", max_length=20)
    period_start: str = Field(pattern=DATE_PATTERN)
    period_end: str = Field(pattern=DATE_PATTERN)

    @model_validator(mode="after")
    def validate_period(self) -> Self:
        if self.period_start > self.period_end:
            raise ValueError("period_start must not be after period_end")
        return self


class TargetUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_value: float | None = Field(default=None, ge=0)
    metric_label: str | None = Field(default=None, max_length=100)
    unit: str | None = Field(default=None, max_length=20)
    period_type: str | None = Field(default=None, max_length=20)
    period_start: str | None = Field(default=None, pattern=DATE_PATTERN)
    period_end: str | None = Field(default=None, pattern=DATE_PATTERN)


def _payload(target: PerformanceTarget) -> dict[str, Any]:
    return {
        "id": target.id,
        "tenant_id": target.tenant_id,
        "agent_id": target.agent_id,
        "metric_key": target.metric_key,
        "metric_label": target.metric_label,
        "target_value": target.target_value,
        "unit": target.unit,
        "period_type": target.period_type,
        "period_start": target.period_start,
        "period_end": target.period_end,
        "created_by": target.created_by,
        "created_at": target.created_at.isoformat() if target.created_at else None,
        "updated_at": target.updated_at.isoformat() if target.updated_at else None,
    }


async def _load_target(target_id: str, db: DB) -> PerformanceTarget:
    target = await db.get(PerformanceTarget, target_id)
    if target is None:
        raise _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Target not found")
    return target


async def _ensure_unique(
    db: DB,
    *,
    tenant_id: str,
    agent_id: str,
    metric_key: str,
    period_start: str,
    period_end: str,
    exclude_id: str | None = None,
) -> None:
    statement = select(PerformanceTarget.id).where(
        PerformanceTarget.tenant_id == tenant_id,
        PerformanceTarget.agent_id == agent_id,
        PerformanceTarget.metric_key == metric_key,
        PerformanceTarget.period_start == period_start,
        PerformanceTarget.period_end == period_end,
    )
    if exclude_id is not None:
        statement = statement.where(PerformanceTarget.id != exclude_id)
    if (await db.execute(statement)).first() is not None:
        raise _error(
            status.HTTP_409_CONFLICT,
            "DUPLICATE",
            "Target already exists for this agent, metric, and period",
        )


@router.get("/")
async def list_targets(
    current_user: RoleAny,
    db: DB,
    tenant_id: str | None = None,
    agent_id: str | None = None,
    period_type: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    if not current_user.is_superadmin and tenant_id not in (
        None,
        current_user.tenant_id,
    ):
        raise _error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "Access denied")

    statement = select(PerformanceTarget)
    if tenant_id is not None:
        statement = statement.where(PerformanceTarget.tenant_id == tenant_id)
    elif not current_user.is_superadmin:
        statement = statement.where(
            PerformanceTarget.tenant_id == current_user.tenant_id
        )
    if agent_id:
        statement = statement.where(PerformanceTarget.agent_id == agent_id)
    if period_type:
        statement = statement.where(PerformanceTarget.period_type == period_type)

    total = int(
        (
            await db.execute(
                select(func.count()).select_from(statement.order_by(None).subquery())
            )
        ).scalar_one()
    )
    result = await db.execute(
        statement.order_by(
            PerformanceTarget.agent_id.asc(),
            PerformanceTarget.metric_key.asc(),
            PerformanceTarget.period_start.asc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = result.scalars().all()
    return {
        "ok": True,
        "data": [_payload(row) for row in rows],
        "meta": {"total": total, "page": page, "page_size": page_size},
    }


@router.get("/by-agent/{agent_id}")
async def get_agent_targets(
    agent_id: str,
    current_user: RoleAny,
    db: DB,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    resolved_tenant = resolve_tenant_id(current_user, tenant_id)
    rows = (
        (
            await db.execute(
                select(PerformanceTarget)
                .where(
                    PerformanceTarget.tenant_id == resolved_tenant,
                    PerformanceTarget.agent_id == agent_id,
                )
                .order_by(
                    PerformanceTarget.metric_key.asc(),
                    PerformanceTarget.period_start.asc(),
                )
            )
        )
        .scalars()
        .all()
    )
    return {
        "ok": True,
        "data": {row.metric_key: _payload(row) for row in rows},
    }


@router.post("/")
async def create_target(
    body: TargetRequest,
    current_user: RoleAdmin,
    db: DB,
) -> dict[str, Any]:
    tenant_id = resolve_tenant_id(current_user, body.tenant_id)
    await ensure_tenant_exists(db, tenant_id)
    await _ensure_unique(
        db,
        tenant_id=tenant_id,
        agent_id=body.agent_id,
        metric_key=body.metric_key,
        period_start=body.period_start,
        period_end=body.period_end,
    )
    target = PerformanceTarget(
        **body.model_dump(exclude={"tenant_id"}),
        tenant_id=tenant_id,
        created_by=current_user.id,
    )
    db.add(target)
    await commit_or_error(db, conflict_message="Target conflicts with existing data")
    return {"ok": True, "data": _payload(target)}


@router.post("/batch")
async def batch_create_targets(
    bodies: list[TargetRequest],
    current_user: RoleAdmin,
    db: DB,
) -> dict[str, Any]:
    if not bodies:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "EMPTY_BATCH",
            "At least one target is required",
        )

    rows: list[PerformanceTarget] = []
    request_keys: set[tuple[str, str, str, str, str]] = set()
    for body in bodies:
        tenant_id = resolve_tenant_id(current_user, body.tenant_id)
        await ensure_tenant_exists(db, tenant_id)
        key = (
            tenant_id,
            body.agent_id,
            body.metric_key,
            body.period_start,
            body.period_end,
        )
        if key in request_keys:
            raise _error(
                status.HTTP_409_CONFLICT,
                "DUPLICATE",
                "Batch contains duplicate targets",
            )
        request_keys.add(key)
        await _ensure_unique(
            db,
            tenant_id=tenant_id,
            agent_id=body.agent_id,
            metric_key=body.metric_key,
            period_start=body.period_start,
            period_end=body.period_end,
        )
        rows.append(
            PerformanceTarget(
                **body.model_dump(exclude={"tenant_id"}),
                tenant_id=tenant_id,
                created_by=current_user.id,
            )
        )

    db.add_all(rows)
    await commit_or_error(
        db, conflict_message="One or more targets conflict with existing data"
    )
    return {
        "ok": True,
        "data": [_payload(row) for row in rows],
        "meta": {"count": len(rows)},
    }


@router.get("/{target_id}")
async def get_target(
    target_id: str,
    current_user: RoleAny,
    db: DB,
) -> dict[str, Any]:
    target = await _load_target(target_id, db)
    ensure_tenant_access(current_user, target.tenant_id)
    return {"ok": True, "data": _payload(target)}


@router.put("/{target_id}")
async def update_target(
    target_id: str,
    body: TargetUpdateRequest,
    current_user: RoleAdmin,
    db: DB,
) -> dict[str, Any]:
    target = await _load_target(target_id, db)
    ensure_tenant_access(current_user, target.tenant_id)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    period_start = changes.get("period_start", target.period_start)
    period_end = changes.get("period_end", target.period_end)
    if period_start > period_end:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "INVALID_PERIOD",
            "period_start must not be after period_end",
        )
    await _ensure_unique(
        db,
        tenant_id=target.tenant_id or current_user.tenant_id,
        agent_id=target.agent_id,
        metric_key=target.metric_key,
        period_start=period_start,
        period_end=period_end,
        exclude_id=target.id,
    )
    for field, value in changes.items():
        setattr(target, field, value)
    await commit_or_error(db, conflict_message="Target conflicts with existing data")
    return {"ok": True, "data": _payload(target)}


@router.delete("/{target_id}")
async def delete_target(
    target_id: str,
    current_user: RoleAdmin,
    db: DB,
) -> dict[str, Any]:
    target = await _load_target(target_id, db)
    ensure_tenant_access(current_user, target.tenant_id)
    await db.delete(target)
    await commit_or_error(
        db, conflict_message="Target is still referenced by other records"
    )
    return {"ok": True, "data": {"message": "Target deleted"}}
