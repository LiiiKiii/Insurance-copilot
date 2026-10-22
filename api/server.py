"""FastAPI application foundation for the Insurance Copilot.

The runtime is created lazily during application startup. Startup failures are
allowed to propagate after best-effort cleanup, and normal shutdown retires the
currently published runtime before closing auxiliary services and database
engines.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from importlib import import_module
from typing import Any

from fastapi import APIRouter, Depends, FastAPI

from admin.db import PROJECT_ROOT, close_db, init_db
from admin.routers import admin_router
from api.briefing_access import require_briefing_access
from api.routers.config import router as config_router
from api.state import RuntimeState
from api.ws import router as websocket_router


RuntimeFactory = Callable[[], RuntimeState]
logger = logging.getLogger(__name__)


class _NullProviderTestService:
    """No-op service used before the shared provider-test module is migrated."""

    async def aclose(self) -> None:
        return None


def _optional_attribute(module_name: str, attribute: str) -> Any | None:
    """Load a staged integration only when its module exists.

    Missing migration-stage modules are optional. Import failures inside an
    existing module still propagate so broken integrations are never hidden.
    """
    try:
        module = import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name == module_name:
            return None
        raise
    return getattr(module, attribute, None)


def _optional_router(module_name: str) -> APIRouter | None:
    router = _optional_attribute(module_name, "router")
    if router is not None and not isinstance(router, APIRouter):
        raise TypeError(f"{module_name}.router must be an APIRouter")
    return router


def _build_provider_test_service() -> Any:
    service_type = _optional_attribute(
        "admin.services.provider_test_service",
        "ProviderTestService",
    )
    return service_type() if service_type is not None else _NullProviderTestService()


async def _close_service(service: Any, *, context: str) -> None:
    try:
        await service.aclose()
    except Exception:
        logger.exception("%s cleanup failed", context)


async def _close_database(*, context: str) -> None:
    try:
        await close_db()
    except Exception:
        logger.exception("Database cleanup %s failed", context)


def create_app(
    runtime: RuntimeState | None = None,
    *,
    runtime_factory: RuntimeFactory | None = None,
    provider_test_service: Any | None = None,
) -> FastAPI:
    """Create an application with one lazily resolved runtime state."""
    if runtime is not None and runtime_factory is not None:
        raise ValueError("Provide either runtime or runtime_factory, not both.")

    factory = runtime_factory or RuntimeState
    test_service = provider_test_service or _build_provider_test_service()
    coordinator_type = _optional_attribute(
        "api.runtime_apply",
        "RuntimeApplyCoordinator",
    )
    runtime_apply_coordinator = (
        coordinator_type() if coordinator_type is not None else None
    )
    feature_model_loader = _optional_attribute(
        "api.feature_models",
        "load_feature_models_from_db",
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        active_runtime: RuntimeState | None = application.state.runtime

        try:
            await init_db()

            if feature_model_loader is not None:
                try:
                    feature_model_loader()
                except Exception:
                    # Feature overrides are best-effort configuration and must
                    # not prevent an otherwise valid runtime from starting.
                    logger.exception("Feature-model configuration could not be loaded")

            if active_runtime is None:
                active_runtime = application.state.runtime_factory()
                application.state.runtime = active_runtime

            if os.environ.get("BUILTIN_KNOWLEDGE_AUTO_SYNC", "1") == "1":
                try:
                    from admin.services.builtin_knowledge import (
                        sync_builtin_knowledge,
                    )

                    # Built-in Markdown is versioned under the repository's
                    # data/knowledge directory, not the configurable Agent
                    # workspace (which normally lives under ~/.nanobot).
                    await sync_builtin_knowledge(PROJECT_ROOT)
                except Exception:
                    # Built-in indexing is repairable through the explicit
                    # sync command and must not make the whole API unavailable.
                    logger.exception("Built-in knowledge synchronization failed")

            await active_runtime.start()
        except BaseException:
            if active_runtime is not None:
                try:
                    await active_runtime.stop()
                except Exception:
                    logger.exception(
                        "Runtime cleanup after startup failure failed"
                    )
            await _close_service(
                test_service,
                context="Provider-test service after startup failure",
            )
            await _close_database(context="after startup failure")
            raise

        try:
            yield
        finally:
            try:
                coordinator = application.state.runtime_apply_coordinator
                if coordinator is not None:
                    # Serialize shutdown with runtime Apply operations so the
                    # currently published runtime is retired.
                    await coordinator.shutdown(application)
                else:
                    current_runtime = application.state.runtime
                    if current_runtime is not None:
                        await current_runtime.stop()
            except Exception:
                logger.exception("Runtime cleanup during shutdown failed")
            finally:
                await _close_service(
                    test_service,
                    context="Provider-test service during shutdown",
                )
                await _close_database(context="during shutdown")

    application = FastAPI(
        title="Insurance Performance Intelligence Copilot",
        lifespan=lifespan,
    )

    audit_middleware = _optional_attribute(
        "admin.middleware",
        "AdminAuditMiddleware",
    )
    if audit_middleware is not None:
        application.add_middleware(audit_middleware)

    application.state.runtime = runtime
    application.state.runtime_factory = factory
    application.state.provider_test_service = test_service
    application.state.runtime_apply_coordinator = runtime_apply_coordinator

    # Shared platform and prior-stage API routes.
    application.include_router(config_router)

    for module_name in ("api.routers.retrieval", "api.routers.audio"):
        service_router = _optional_router(module_name)
        if service_router is not None:
            application.include_router(service_router)

    # ``api.routers.config`` always exports ``router``; its later-stage feature
    # router is loaded separately to avoid registering the base router twice.
    feature_router = _optional_attribute("api.routers.config", "feature_router")
    if feature_router is not None:
        if not isinstance(feature_router, APIRouter):
            raise TypeError("api.routers.config.feature_router must be an APIRouter")
        application.include_router(feature_router)

    planning_router = _optional_router("api.routers.planning")
    if planning_router is not None:
        application.include_router(planning_router)

    agents_router = _optional_router("api.routers.agents")
    if agents_router is not None:
        application.include_router(agents_router)

    for module_name in ("api.routers.business", "api.routers.sessions"):
        compatibility_router = _optional_router(module_name)
        if compatibility_router is not None:
            application.include_router(compatibility_router)

    briefing_router = _optional_router("api.routers.briefing")
    if briefing_router is not None:
        application.include_router(
            briefing_router, dependencies=[Depends(require_briefing_access)]
        )

    application.include_router(websocket_router)

    # M3 A4 uses one canonical auth path through this registry and adds the
    # knowledge routes there. Do not mount admin.routers.auth a second time.
    application.include_router(admin_router, prefix="/api/admin")

    # Other workstreams' A4 admin routers carry their own final prefixes and
    # are mounted when those modules are present in the merged repository.
    for module_name in (
        "admin.routers.users",
        "admin.routers.audit",
        "admin.routers.models",
        "admin.routers.config",
        "admin.routers.targets",
        "admin.routers.competitions",
        "admin.routers.assessments",
    ):
        staged_router = _optional_router(module_name)
        if staged_router is not None:
            application.include_router(staged_router)

    @application.get("/api/health")
    async def health() -> dict[str, Any]:
        """Return server availability without exposing configuration details."""
        active_runtime: RuntimeState | None = application.state.runtime
        agent_status = (
            "not_started"
            if active_runtime is None
            else "running"
            if active_runtime.is_running
            else "not_running"
        )
        return {
            "status": "ok",
            "agent_loop": agent_status,
        }

    return application


# ASGI entry point. RuntimeState remains lazy until the host enters lifespan.
app = create_app()
