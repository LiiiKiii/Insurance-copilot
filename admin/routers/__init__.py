"""Stage-scoped administration router registry.

A4 intentionally exposes only authentication and knowledge management. Other
administration domains remain outside this migration round.
"""

from fastapi import APIRouter

from admin.routers.auth import router as auth_router
from admin.routers.knowledge import router as knowledge_router


# Each child endpoint declares its own CurrentUser/Role dependency. Keeping the
# registry free of a second authentication dependency lets /auth/me report a
# live user's revoked admin state and avoids duplicate database lookups.
admin_router = APIRouter()
admin_router.include_router(auth_router, prefix="/auth", tags=["Admin - Auth"])
admin_router.include_router(
    knowledge_router,
    prefix="/knowledge-bases",
    tags=["Admin - Knowledge"],
)

__all__ = ["admin_router"]
