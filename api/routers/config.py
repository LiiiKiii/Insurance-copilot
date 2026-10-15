"""Read-only runtime configuration status endpoint."""

from __future__ import annotations

from typing import Annotated
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from admin.dependencies import DB, RoleAdmin
from admin.services.provider_test_service import ProviderTestService, get_provider_test_service
from api.feature_models import (
    FEATURE_META,
    FEATURE_SLUGS,
    get_feature_models_snapshot,
    reset_all_feature_models,
    save_feature_model_to_db,
)
from api.runtime_apply import RuntimeApplyError, build_candidate
from api.runtime_config import (
    RuntimeConfigurationError,
    RuntimePersistenceSnapshot,
    persist_runtime_config,
    restore_runtime_config,
)
from admin.config_bridge import get_default_model_config


router = APIRouter(prefix="/api/config")
feature_router = APIRouter(prefix="/api/feature-models")
_FEATURES = tuple(
    (slug, FEATURE_META[slug]["label"], FEATURE_META[slug]["desc"])
    for slug in FEATURE_SLUGS
)
_FEATURE_SLUGS = frozenset(item[0] for item in _FEATURES)


class ApiConfigRequest(BaseModel):
    """Runtime provider request retaining the Original JSON field names."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    api_key: str = Field(default="", alias="apiKey", max_length=10_000)
    provider: str = Field(default="openrouter", min_length=1, max_length=50)
    model: str = Field(default="openai/gpt-5.2", min_length=1, max_length=200)
    base_url: str = Field(default="https://openrouter.ai/api/v1", alias="baseUrl", max_length=500)
    enable_thinking: bool = Field(default=False, alias="enableThinking")


class FeatureModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str = Field(min_length=1, max_length=50)
    model: str = Field(max_length=200)


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


@router.post("/apply")
async def apply_runtime_provider(
    request: Request, _: RoleAdmin, db: DB, body: ApiConfigRequest | None = None
) -> dict[str, str | bool]:
    """Persist then publish a validated runtime without plaintext key storage."""
    snapshot: RuntimePersistenceSnapshot | None = None
    try:
        if body is None or not body.api_key:
            default = get_default_model_config()
            if not default or not isinstance(default.get("api_key"), str) or not default["api_key"]:
                return {"ok": False, "error": "Runtime credentials are required."}
            body = ApiConfigRequest(
                provider=default.get("provider") or "openrouter",
                apiKey=default["api_key"],
                baseUrl=default.get("base_url") or "",
                model=default.get("model_id") or "",
            )
        candidate = build_candidate(
            request.app.state.runtime,
            provider=body.provider,
            model=body.model,
            api_key=body.api_key,
            base_url=body.base_url,
            enable_thinking=body.enable_thinking,
        )

        async def persist() -> None:
            nonlocal snapshot
            snapshot = await persist_runtime_config(
                db,
                provider=body.provider,
                model=body.model,
                api_key=body.api_key,
                base_url=body.base_url,
                enable_thinking=body.enable_thinking,
            )

        async def restore() -> None:
            if snapshot is not None:
                await restore_runtime_config(db, snapshot)

        await request.app.state.runtime_apply_coordinator.replace(
            request.app,
            candidate,
            before_publish=persist,
            on_unpublished_failure=restore,
        )
    except (RuntimeApplyError, RuntimeConfigurationError) as exc:
        return {"ok": False, "error": str(exc)}
    except Exception:
        return {"ok": False, "error": "Runtime configuration could not be applied."}
    return {"ok": True, "message": f"Provider switched: openrouter / {body.model} (thinking=off)"}


@feature_router.get("")
async def list_feature_models(_: RoleAdmin) -> dict[str, Any]:
    overrides = get_feature_models_snapshot()
    return {"ok": True, "data": [
        {"slug": slug, "label": label, "desc": desc, "model": overrides.get(slug, "")}
        for slug, label, desc in _FEATURES
    ]}


@feature_router.post("")
async def update_feature_model(body: FeatureModelRequest, _: RoleAdmin, db: DB) -> dict[str, Any]:
    slug = body.slug
    if slug not in _FEATURE_SLUGS:
        return {"ok": False, "error": f"Unknown feature slug: {slug}"}
    model = body.model.strip()
    try:
        await save_feature_model_to_db(slug, model, db)
    except Exception:
        await db.rollback()
        return {"ok": False, "error": "Feature model configuration could not be saved."}
    return {"ok": True, "slug": slug, "model": model}


@feature_router.post("/reset")
async def reset_feature_models(_: RoleAdmin, db: DB) -> dict[str, Any]:
    try:
        await reset_all_feature_models(db)
    except Exception:
        await db.rollback()
        return {"ok": False, "error": "Feature model configuration could not be reset."}
    return {"ok": True, "message": "All feature model overrides cleared"}
