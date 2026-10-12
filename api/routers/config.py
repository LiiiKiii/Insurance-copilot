"""Read-only runtime configuration status endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request


router = APIRouter(prefix="/api/config")


@router.get("/status")
async def config_status(request: Request) -> dict[str, bool]:
    """Report whether the current application's runtime loop is running.

    ``configured`` is a runtime-readiness signal only.  It does not validate
    provider credentials or expose provider, model, endpoint, or key details.
    """
    runtime = getattr(request.app.state, "runtime", None)
    configured = runtime is not None and bool(getattr(runtime, "is_running", False))
    return {"ok": True, "configured": configured}
