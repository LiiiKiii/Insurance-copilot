"""Read-only runtime configuration status endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from admin.dependencies import RoleAdmin
from admin.services.provider_test_service import ProviderTestService, get_provider_test_service


router = APIRouter(prefix="/api/config")


class ApiConfigRequest(BaseModel):
    """Non-persistent runtime provider test request, retaining original JSON names."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    api_key: str = Field(alias="apiKey", min_length=1, max_length=10_000)
    provider: str = Field(default="openrouter", min_length=1, max_length=50)
    model: str = Field(default="openai/gpt-5.2", min_length=1, max_length=200)
    base_url: str = Field(default="https://openrouter.ai/api/v1", alias="baseUrl", max_length=500)
    enable_thinking: bool = Field(default=False, alias="enableThinking")


@router.get("/status")
async def config_status(request: Request) -> dict[str, bool]:
    """Report whether the current application's runtime loop is running.

    ``configured`` is a runtime-readiness signal only.  It does not validate
    provider credentials or expose provider, model, endpoint, or key details.
    """
    runtime = getattr(request.app.state, "runtime", None)
    configured = runtime is not None and bool(getattr(runtime, "is_running", False))
    return {"ok": True, "configured": configured}


@router.post("/test")
async def test_runtime_provider(
    body: ApiConfigRequest,
    _: RoleAdmin,
    service: Annotated[ProviderTestService, Depends(get_provider_test_service)],
) -> dict[str, str | bool]:
    """Test a caller-supplied key once without persisting or applying it."""

    result = await service.test(
        provider=body.provider,
        model=body.model,
        api_key=body.api_key,
        base_url=body.base_url,
    )
    return {"ok": result.ok, "message": result.message}
