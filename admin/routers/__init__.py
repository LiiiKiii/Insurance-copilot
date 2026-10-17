"""Stage-scoped administration router registry.

A4 intentionally exposes only authentication and knowledge management. Other
administration domains remain outside this migration round.
"""

from fastapi import APIRouter, Depends

from admin.dependencies import require_admin_auth
from admin.routers.auth import router as auth_router
from admin.routers.knowledge import router as knowledge_router


admin_router = APIRouter(dependencies=[Depends(require_admin_auth)])
admin_router.include_router(auth_router, prefix="/auth", tags=["Admin - Auth"])
admin_router.include_router(
    knowledge_router,
    prefix="/knowledge-bases",
    tags=["Admin - Knowledge"],
)

__all__ = ["admin_router"]
