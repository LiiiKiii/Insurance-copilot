"""Candidate-first runtime replacement coordination for the single-process app."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from collections.abc import Awaitable, Callable
from typing import AsyncIterator

from api.state import RuntimeState


logger = logging.getLogger(__name__)
_RETIREMENT_WAIT_SECONDS = 5


class RuntimeApplyError(ValueError):
    """A requested runtime configuration is not safely supported."""


class RuntimeApplyCoordinator:
    """Serialize replacements and drain direct agent turns before publication."""

    def __init__(self) -> None:
        self._apply_lock = asyncio.Lock()
        self._condition = asyncio.Condition()
        self._applying = False
        self._active_turns = 0
        self._shutting_down = False
        self._retirement_tasks: set[asyncio.Task[bool]] = set()
        self._retiring_runtime_ids: set[int] = set()

    @asynccontextmanager
    async def turn(self) -> AsyncIterator[None]:
        async with self._condition:
            while self._applying:
                await self._condition.wait()
            self._active_turns += 1
        try:
            yield
        finally:
            async with self._condition:
                self._active_turns -= 1
                if self._active_turns == 0:
                    self._condition.notify_all()

    async def _gate_and_drain(self) -> None:
        async with self._condition:
            self._applying = True
        try:
            async with self._condition:
                while self._active_turns:
                    await self._condition.wait()
        except BaseException:
            await self._clear_gate()
            raise

    async def _clear_gate(self) -> None:
        async with self._condition:
            self._applying = False
            self._condition.notify_all()

    async def _retire(self, runtime: RuntimeState) -> bool:
        try:
            await runtime.stop()
        except Exception:
            logger.exception("Previous runtime cleanup after replacement failed")
            return False
        return True

    def _register_retirement(self, runtime: RuntimeState) -> asyncio.Task[bool]:
        """Own retirement before the caller reaches a cancellation point."""
        runtime_id = id(runtime)
        if runtime_id in self._retiring_runtime_ids:
            raise RuntimeError("Runtime retirement was registered twice.")
        self._retiring_runtime_ids.add(runtime_id)
        task = asyncio.create_task(self._retire(runtime), name="insurance-copilot-runtime-retirement")
        self._retirement_tasks.add(task)

        def completed(done: asyncio.Task[bool]) -> None:
            self._retirement_tasks.discard(done)
            self._retiring_runtime_ids.discard(runtime_id)
            try:
                done.result()
            except asyncio.CancelledError:
                logger.warning("Runtime retirement task was cancelled")
            except Exception:
                # _retire handles ordinary stop failures; this guards an
                # unexpected task failure without exposing its contents.
                logger.exception("Runtime retirement task failed unexpectedly")

        task.add_done_callback(completed)
        return task

    async def _wait_for_retirements(self) -> None:
        pending = tuple(self._retirement_tasks)
        if not pending:
            return
        try:
            await asyncio.wait_for(asyncio.shield(asyncio.gather(*pending, return_exceptions=True)), _RETIREMENT_WAIT_SECONDS)
        except asyncio.TimeoutError:
            logger.error("Timed out waiting for previous runtime retirement during shutdown")

    async def replace(
        self,
        application,  # type: ignore[no-untyped-def]
        candidate: RuntimeState,
        *,
        before_publish: Callable[[], Awaitable[None]] | None = None,
        on_unpublished_failure: Callable[[], Awaitable[None]] | None = None,
    ) -> bool:
        """Publish a started candidate after draining old direct turns.

        Candidate and old runtimes have independent MessageBus instances.  The
        candidate is therefore safe to start before publication; once published
        it remains available even if best-effort old-runtime cleanup fails.
        """
        async with self._apply_lock:
            if self._shutting_down:
                raise RuntimeApplyError("Runtime is shutting down.")
            published = False
            gated = False
            try:
                await candidate.start()
                if before_publish is not None:
                    await before_publish()
                await self._gate_and_drain()
                gated = True
                old = application.state.runtime
                application.state.runtime = candidate
                published = True
                # Registration has no intervening await, so request
                # cancellation cannot strand a published old runtime.
                if old is not None:
                    retirement = self._register_retirement(old)
                    return await asyncio.shield(retirement)
                return True
            except BaseException:
                if not published:
                    if on_unpublished_failure is not None:
                        await on_unpublished_failure()
                    await candidate.stop()
                raise
            finally:
                if gated:
                    await self._clear_gate()

    async def shutdown(self, application) -> None:  # type: ignore[no-untyped-def]
        """Serialize shutdown with Apply and retire the currently published runtime."""
        self._shutting_down = True
        async with self._apply_lock:
            gated = False
            try:
                await self._gate_and_drain()
                gated = True
                await self._wait_for_retirements()
                runtime = application.state.runtime
                if runtime is None:
                    return
                try:
                    await runtime.stop()
                except Exception:
                    # A failed stop cannot remain a routable runtime once the
                    # shutdown gate is released.
                    application.state.runtime = None
                    raise
            finally:
                if gated:
                    await self._clear_gate()


def build_candidate(
    current: RuntimeState | None, *, provider: str, model: str, api_key: str, base_url: str, enable_thinking: bool
) -> RuntimeState:
    """Construct but do not start a safe replacement state.

    The only registered runtime backend is OpenRouter.  Submitted credentials
    live only in this in-memory candidate and are never written to SystemConfig.
    """
    if provider.strip().casefold() != "openrouter":
        raise RuntimeApplyError("The requested provider is not supported by this runtime.")
    if base_url.rstrip("/") != "https://openrouter.ai/api/v1":
        raise RuntimeApplyError("The requested provider endpoint is not permitted.")
    if enable_thinking:
        raise RuntimeApplyError("Thinking mode is not supported by the current runtime backend.")
    if current is None or not isinstance(current, RuntimeState):
        raise RuntimeApplyError("The current runtime cannot be safely replaced.")
    config = current.config.model_copy(deep=True)
    config.agents.defaults.provider = "openrouter"
    config.agents.defaults.model = model
    config.providers.openrouter.api_key = api_key
    config.providers.openrouter.api_base = "https://openrouter.ai/api/v1"
    return RuntimeState(config=config, workspace=current.workspace)
