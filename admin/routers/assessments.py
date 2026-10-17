"""Tenant-scoped agent assessment administration endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from admin.dependencies import DB, RoleAdmin, RoleAny, _error
from admin.models.assessment import AgentAssessment
from admin.routers._business import (
    commit_or_error,
    ensure_tenant_access,
    ensure_tenant_exists,
    resolve_tenant_id,
)

router = APIRouter(prefix="/api/admin/assessments", tags=["admin-assessments"])


class AssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str | None = Field(default=None, max_length=36)
    agent_id: str = Field(min_length=1, max_length=20)
    subject: str = Field(min_length=1, max_length=64)
    target_value: float | None = None
    current_value: float | None = None
    status: str | None = Field(default=None, max_length=32)
    remark: str | None = None


class AssessmentUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str | None = Field(default=None, min_length=1, max_length=64)
    target_value: float | None = None
    current_value: float | None = None
    status: str | None = Field(default=None, max_length=32)
    remark: str | None = None


def _payload(row: AgentAssessment) -> dict[str, Any]:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "agent_id": row.agent_id,
        "subject": row.subject,
        "target_value": row.target_value,
        "current_value": row.current_value,
        "status": row.status,
        "remark": row.remark,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def _load_assessment(assessment_id: str, db: DB) -> AgentAssessment:
    assessment = await db.get(AgentAssessment, assessment_id)
    if assessment is None:
        raise _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Assessment not found")
    return assessment


async def _ensure_unique(
    db: DB,
    *,
    tenant_id: str,
    agent_id: str,
    subject: str,
    exclude_id: str | None = None,
) -> None:
    statement = select(AgentAssessment.id).where(
        AgentAssessment.tenant_id == tenant_id,
        AgentAssessment.agent_id == agent_id,
        AgentAssessment.subject == subject,
    )
    if exclude_id is not None:
        statement = statement.where(AgentAssessment.id != exclude_id)
    if (await db.execute(statement)).first() is not None:
        raise _error(
            status.HTTP_409_CONFLICT,
            "DUPLICATE",
            "Assessment already exists for this agent and subject",
        )


@router.get("/")
async def list_assessments(
    current_user: RoleAny,
    db: DB,
    tenant_id: str | None = None,
    agent_id: str | None = None,
    assessment_status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    if not current_user.is_superadmin and tenant_id not in (
        None,
        current_user.tenant_id,
    ):
        raise _error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "Access denied")

    statement = select(AgentAssessment)
    if tenant_id is not None:
        statement = statement.where(AgentAssessment.tenant_id == tenant_id)
    elif not current_user.is_superadmin:
        statement = statement.where(AgentAssessment.tenant_id == current_user.tenant_id)
    if agent_id:
        statement = statement.where(AgentAssessment.agent_id == agent_id)
    if assessment_status:
        statement = statement.where(AgentAssessment.status == assessment_status)

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
                statement.order_by(
                    AgentAssessment.agent_id.asc(),
                    AgentAssessment.subject.asc(),
                    AgentAssessment.id.asc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return {
        "ok": True,
        "data": [_payload(row) for row in rows],
        "meta": {"total": total, "page": page, "page_size": page_size},
    }


@router.post("/")
async def create_assessment(
    body: AssessmentRequest,
    current_user: RoleAdmin,
    db: DB,
) -> dict[str, Any]:
    tenant_id = resolve_tenant_id(current_user, body.tenant_id)
    await ensure_tenant_exists(db, tenant_id)
    await _ensure_unique(
        db,
        tenant_id=tenant_id,
        agent_id=body.agent_id,
        subject=body.subject,
    )
    assessment = AgentAssessment(
        **body.model_dump(exclude={"tenant_id"}),
        tenant_id=tenant_id,
    )
    db.add(assessment)
    await commit_or_error(
        db, conflict_message="Assessment conflicts with existing data"
    )
    return {"ok": True, "data": _payload(assessment)}


@router.get("/{assessment_id}")
async def get_assessment(
    assessment_id: str,
    current_user: RoleAny,
    db: DB,
) -> dict[str, Any]:
    assessment = await _load_assessment(assessment_id, db)
    ensure_tenant_access(current_user, assessment.tenant_id)
    return {"ok": True, "data": _payload(assessment)}


@router.put("/{assessment_id}")
async def update_assessment(
    assessment_id: str,
    body: AssessmentUpdateRequest,
    current_user: RoleAdmin,
    db: DB,
) -> dict[str, Any]:
    assessment = await _load_assessment(assessment_id, db)
    ensure_tenant_access(current_user, assessment.tenant_id)
    changes = body.model_dump(exclude_unset=True)
    if "subject" in changes and changes["subject"] is None:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "INVALID_SUBJECT",
            "Assessment subject cannot be null",
        )
    subject = changes.get("subject", assessment.subject)
    await _ensure_unique(
        db,
        tenant_id=assessment.tenant_id or current_user.tenant_id,
        agent_id=assessment.agent_id,
        subject=subject,
        exclude_id=assessment.id,
    )
    for field, value in changes.items():
        setattr(assessment, field, value)
    await commit_or_error(
        db, conflict_message="Assessment conflicts with existing data"
    )
    return {"ok": True, "data": _payload(assessment)}


@router.delete("/{assessment_id}")
async def delete_assessment(
    assessment_id: str,
    current_user: RoleAdmin,
    db: DB,
) -> dict[str, Any]:
    assessment = await _load_assessment(assessment_id, db)
    ensure_tenant_access(current_user, assessment.tenant_id)
    await db.delete(assessment)
    await commit_or_error(
        db, conflict_message="Assessment is still referenced by other records"
    )
    return {"ok": True, "data": {"message": "Assessment deleted"}}
