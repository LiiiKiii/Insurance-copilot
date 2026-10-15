"""Read-only runtime configuration status endpoint."""

from __future__ import annotations

from typing import Annotated

import json
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from admin.config_bridge import invalidate
from admin.dependencies import DB, RoleAdmin
from admin.models.config import SystemConfig
from admin.models.model_config import ModelConfig
from admin.services.provider_test_service import ProviderTestService, get_provider_test_service
from api.runtime_apply import RuntimeApplyError, build_candidate


router = APIRouter(prefix="/api/config")
feature_router = APIRouter(prefix="/api/feature-models")
_FEATURE_CONFIG_KEY = "runtime.feature_models"
_FEATURES = (
    ("chat", "Chat", "Interactive assistant responses"),
    ("embedding", "Embedding", "Semantic search embeddings"),
    ("multimodal", "Multimodal", "Image and document understanding"),
    ("ocr", "OCR", "Document text extraction"),
    ("image_gen", "Image generation", "Text-to-image generation"),
    ("asr", "Speech recognition", "Speech-to-text"),
    ("tts", "Speech synthesis", "Text-to-speech"),
    ("rerank", "Reranking", "Search result reranking"),
)
_FEATURE_SLUGS = frozenset(item[0] for item in _FEATURES)


class ApiConfigRequest(BaseModel):
    """Non-persistent runtime provider test request, retaining original JSON names."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    api_key: str = Field(alias="apiKey", min_length=1, max_length=10_000)
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
async def apply_runtime_provider(body: ApiConfigRequest, request: Request, _: RoleAdmin) -> dict[str, str | bool]:
    """Replace the local runtime only after a candidate has started successfully."""
    try:
        candidate = build_candidate(
            request.app.state.runtime,
            provider=body.provider,
            model=body.model,
            api_key=body.api_key,
            base_url=body.base_url,
            enable_thinking=body.enable_thinking,
        )
        await request.app.state.runtime_apply_coordinator.replace(request.app, candidate)
    except RuntimeApplyError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception:
        return {"ok": False, "error": "Runtime configuration could not be applied."}
    return {"ok": True, "message": f"Provider switched: openrouter / {body.model} (thinking=off)"}


async def _feature_overrides(db: DB) -> dict[str, str]:
    row = (await db.execute(select(SystemConfig).where(
        SystemConfig.tenant_id.is_(None), SystemConfig.config_key == _FEATURE_CONFIG_KEY
    ))).scalar_one_or_none()
    if row is None:
        return {}
    try:
        value = json.loads(row.config_value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(value, dict):
        return {}
    return {slug: model for slug, model in value.items() if slug in _FEATURE_SLUGS and isinstance(model, str)}


@feature_router.get("")
async def list_feature_models(_: RoleAdmin, db: DB) -> dict[str, Any]:
    overrides = await _feature_overrides(db)
    return {"ok": True, "data": [
        {"slug": slug, "label": label, "desc": desc, "model": overrides.get(slug, "")}
        for slug, label, desc in _FEATURES
    ]}


@feature_router.post("")
async def update_feature_model(body: FeatureModelRequest, _: RoleAdmin, db: DB) -> dict[str, Any]:
    slug = body.slug.strip()
    if slug not in _FEATURE_SLUGS:
        return {"ok": False, "error": f"Unknown feature slug: {slug}"}
    model = body.model.strip()
    if model:
        allowed = (await db.execute(select(ModelConfig.id).where(
            ModelConfig.tenant_id.is_(None), ModelConfig.enabled.is_(True),
            ModelConfig.model_type == "llm", ModelConfig.provider == "openrouter", ModelConfig.model_id == model,
        ))).scalar_one_or_none()
        if allowed is None:
            return {"ok": False, "error": "The requested model is not an enabled global runtime model."}
    try:
        overrides = await _feature_overrides(db)
        if model:
            overrides[slug] = model
        else:
            overrides.pop(slug, None)
        row = (await db.execute(select(SystemConfig).where(
            SystemConfig.tenant_id.is_(None), SystemConfig.config_key == _FEATURE_CONFIG_KEY
        ))).scalar_one_or_none()
        if row is None:
            row = SystemConfig(config_key=_FEATURE_CONFIG_KEY, config_value=json.dumps(overrides, sort_keys=True), config_type="json", description="Feature model overrides")
            db.add(row)
        else:
            row.config_value = json.dumps(overrides, sort_keys=True)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        return {"ok": False, "error": "Feature model configuration could not be saved."}
    invalidate(_FEATURE_CONFIG_KEY)
    return {"ok": True, "data": {"slug": slug, "model": model}}


@feature_router.post("/reset")
async def reset_feature_models(_: RoleAdmin, db: DB) -> dict[str, Any]:
    try:
        row = (await db.execute(select(SystemConfig).where(
            SystemConfig.tenant_id.is_(None), SystemConfig.config_key == _FEATURE_CONFIG_KEY
        ))).scalar_one_or_none()
        if row is not None:
            await db.delete(row)
            await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        return {"ok": False, "error": "Feature model configuration could not be reset."}
    invalidate(_FEATURE_CONFIG_KEY)
    return {"ok": True}
