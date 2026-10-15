"""Original audit reader paths with live-user tenant boundaries."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from admin.dependencies import DB, RoleAny, require_admin_auth, is_admin_role
from admin.models.audit import AiAuditLog, ErrorLog, RequestLog

router = APIRouter(
    prefix="/api/admin/logs", tags=["Admin - Audit"],
    dependencies=[Depends(require_admin_auth)],
)


def _date(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid ISO date") from exc


def _dates(query, model, from_date: str | None, to_date: str | None):
    start, end = _date(from_date), _date(to_date)
    if start is not None:
        query = query.where(model.created_at >= start)
    if end is not None:
        query = query.where(model.created_at <= end)
    return query


async def _page(db, query, model, page: int, page_size: int, fields):
    total = (await db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))) or 0
    rows = (await db.scalars(query.order_by(model.created_at.desc(), model.id.desc()).offset((page - 1) * page_size).limit(page_size))).all()
    return {
        "ok": True,
        "data": [{name: transform(getattr(row, name)) for name, transform in fields.items()} for row in rows],
        "meta": {"page": page, "page_size": page_size, "total": total},
    }


def _identity(value):
    return value


def _timestamp(value):
    return value.isoformat() if value else None


@router.get("/requests")
async def list_request_logs(
    current_user: RoleAny, db: DB,
    tenant_id: str | None = None, user_id: str | None = None,
    endpoint: str | None = None, method: str | None = None,
    status_code: int | None = None, from_date: str | None = None,
    to_date: str | None = None, page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    query = select(RequestLog)
    if not current_user.is_superadmin:
        query = query.where(RequestLog.tenant_id == current_user.tenant_id)
        if not is_admin_role(current_user):
            query = query.where(RequestLog.user_id == current_user.id)
    if tenant_id is not None:
        query = query.where(RequestLog.tenant_id == tenant_id)
    if user_id is not None:
        query = query.where(RequestLog.user_id == user_id)
    if endpoint is not None:
        query = query.where(RequestLog.endpoint.ilike(f"%{endpoint}%"))
    if method is not None:
        query = query.where(RequestLog.method == method.upper())
    if status_code is not None:
        query = query.where(RequestLog.status_code == status_code)
    query = _dates(query, RequestLog, from_date, to_date)
    return await _page(db, query, RequestLog, page, page_size, {
        "id": _identity, "tenant_id": _identity, "user_id": _identity,
        "endpoint": _identity, "method": _identity, "status_code": _identity,
        "latency_ms": _identity, "ip_address": _identity,
        "created_at": _timestamp,
    })


@router.get("/ai-audit")
async def list_ai_audit_logs(
    current_user: RoleAny, db: DB,
    session_id: str | None = None, agent_id: str | None = None,
    has_compliance_issue: bool | None = None,
    from_date: str | None = None, to_date: str | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
):
    query = select(AiAuditLog)
    if not current_user.is_superadmin:
        query = query.where(AiAuditLog.tenant_id == current_user.tenant_id)
        if not is_admin_role(current_user):
            query = query.where(AiAuditLog.user_id == current_user.id)
    if session_id is not None:
        query = query.where(AiAuditLog.session_id == session_id)
    if agent_id is not None:
        query = query.where(AiAuditLog.agent_id == agent_id)
    if has_compliance_issue is not None:
        query = query.where(AiAuditLog.has_compliance_issue == has_compliance_issue)
    query = _dates(query, AiAuditLog, from_date, to_date)
    return await _page(db, query, AiAuditLog, page, page_size, {
        "id": _identity, "session_id": _identity, "agent_id": _identity,
        "user_query": lambda value: value[:200],
        "ai_response": lambda value: value[:500],
        "tools_called": _identity, "model_id": _identity,
        "prompt_tokens": _identity, "completion_tokens": _identity,
        "has_compliance_issue": _identity, "compliance_notes": _identity,
        "created_at": _timestamp,
    })


@router.get("/errors")
async def list_error_logs(
    current_user: RoleAny, db: DB,
    level: str | None = None, from_date: str | None = None,
    to_date: str | None = None, page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    query = select(ErrorLog)
    if not current_user.is_superadmin:
        query = query.where(ErrorLog.tenant_id == current_user.tenant_id)
    if level is not None:
        query = query.where(ErrorLog.level == level)
    query = _dates(query, ErrorLog, from_date, to_date)
    fields = {
        "id": _identity, "tenant_id": _identity, "level": _identity,
        "message": _identity, "created_at": _timestamp,
    }
    if current_user.is_superadmin or is_admin_role(current_user):
        fields.update({"stack_trace": _identity, "context": _identity})
    return await _page(db, query, ErrorLog, page, page_size, fields)
