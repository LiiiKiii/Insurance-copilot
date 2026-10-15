"""FastAPI application foundation for the Insurance Copilot.

Failure policy:

* The default ``RuntimeState`` is built during application startup, not module
  import.  Configuration or provider-resolution failures therefore prevent the
  server from starting and are allowed to propagate to the ASGI host.
* A ``RuntimeState.start`` failure is likewise propagated after its best-effort
  cleanup.  It is never converted into a healthy application.
* If the AgentLoop task later terminates, this module does not restart it.
  Health remains available but reports ``agent_loop: not_running``; normal
  lifespan shutdown still calls ``RuntimeState.stop``.

The default ``app`` is importable by ASGI servers.  Use ``create_app`` to
inject a RuntimeState or a state factory in tests and alternate hosts.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from admin.routers.auth import router as admin_auth_router
from admin.routers.config import router as admin_config_router
from admin.routers.models import router as admin_models_router
from admin.services.provider_test_service import ProviderTestService
from api.runtime_apply import RuntimeApplyCoordinator
from api.feature_models import load_feature_models_from_db
from api.routers.config import feature_router, router as config_router
from api.routers.planning import router as planning_router
from api.state import RuntimeState
from api.ws import router as websocket_router


RuntimeFactory = Callable[[], RuntimeState]
logger = logging.getLogger(__name__)


def create_app(
    runtime: RuntimeState | None = None,
    *,
    runtime_factory: RuntimeFactory | None = None,
    provider_test_service: ProviderTestService | None = None,
) -> FastAPI:
    """Create an application with exactly one lazily-resolved RuntimeState.

    Supplying a runtime is intended for dependency injection.  Omitting it
    leaves construction until lifespan startup, so importing ``api.server``
    does not create an AgentLoop or validate live provider configuration.
    """
    if runtime is not None and runtime_factory is not None:
        raise ValueError("Provide either runtime or runtime_factory, not both.")

    factory = runtime_factory or RuntimeState
    test_service = provider_test_service or ProviderTestService()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        active_runtime: RuntimeState | None = application.state.runtime

        try:
            # Feature overrides are best-effort configuration and must not
            # make an otherwise valid runtime unavailable.
            load_feature_models_from_db()
            if active_runtime is None:
                active_runtime = application.state.runtime_factory()
                application.state.runtime = active_runtime

            await active_runtime.start()
        except BaseException:
            # RuntimeState.stop is idempotent and clears any task that startup
            # may have created before failing.  Preserve the startup failure.
            if active_runtime is not None:
                try:
                    await active_runtime.stop()
                except Exception:
                    # A cleanup failure must not disguise the original startup
                    # error, but it remains observable to server operators.
                    logger.exception("RuntimeState cleanup after startup failure failed")
            await test_service.aclose()
            raise

        try:
            yield
        finally:
            try:
                # Serialize shutdown with Apply so this always retires the
                # currently published runtime, not the startup-local instance.
                await application.state.runtime_apply_coordinator.shutdown(application)
            except Exception:
                logger.exception("Runtime cleanup during shutdown failed")
            finally:
                await test_service.aclose()

    application = FastAPI(
        title="Insurance Performance Intelligence Copilot",
        lifespan=lifespan,
    )
    application.state.runtime = runtime
    application.state.runtime_factory = factory
    application.state.provider_test_service = test_service
    application.state.runtime_apply_coordinator = RuntimeApplyCoordinator()
    application.include_router(admin_auth_router)
    application.include_router(admin_models_router)
    application.include_router(admin_config_router)
    application.include_router(config_router)
    application.include_router(feature_router)
    application.include_router(planning_router)
    application.include_router(websocket_router)

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


# ASGI entry point.  RuntimeState remains lazy until the host enters lifespan.
app = create_app()
