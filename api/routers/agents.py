"""Agent identifiers for the existing target-management client."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from admin.dependencies import DB, RoleAny
from admin.models.user import User


router = APIRouter()


@router.get("/api/agents-list")
async def list_agent_ids(current_user: RoleAny, db: DB) -> dict:
    """Return active usernames in the caller's tenant for target selection."""
    rows = (
        await db.execute(
            select(User.username)
            .where(
                User.tenant_id == current_user.tenant_id,
                User.is_active.is_(True),
                User.is_superadmin.is_(False),
            )
            .order_by(User.username.asc())
        )
    ).scalars().all()
    return {"ok": True, "data": [{"agent_id": username} for username in rows]}
