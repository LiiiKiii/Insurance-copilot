"""Explicit lifecycle management for the application-owned agent runtime."""

from __future__ import annotations

import asyncio
from pathlib import Path

from nanobot.agent.loop import AgentLoop
from nanobot.agent.tools.insurance.reasoning_layer.composition import (
    build_reasoning_registry,
)
from nanobot.bus.queue import MessageBus
from nanobot.config.loader import load_config
from nanobot.config.schema import Config
from nanobot.providers import OpenAICompatProvider
from nanobot.providers.base import LLMProvider
from nanobot.providers.registry import find_by_name


class RuntimeState:
    """Own the runtime objects that an application lifespan will manage.

    Construction is side-effect free: it resolves configuration and creates the
    provider client, but does not start the agent loop or make LLM requests.
    """

    def __init__(
        self,
        config: Config | None = None,
        provider: LLMProvider | None = None,
        workspace: Path | None = None,
    ) -> None:
        self.config = config or load_config()
        self.workspace = workspace or self.config.workspace_path
        self.bus = MessageBus()
        self.provider = provider or self._create_provider()
        self.tool_registry = build_reasoning_registry()
        self.agent_loop = AgentLoop(
            bus=self.bus,
            provider=self.provider,
            workspace=self.workspace,
            model=self.config.agents.defaults.model,
            tool_registry=self.tool_registry,
        )
        self._agent_task: asyncio.Task[None] | None = None
        self._lifecycle_lock = asyncio.Lock()

    @property
    def agent_task(self) -> asyncio.Task[None] | None:
        """Return the background AgentLoop task, if it has been started."""
        return self._agent_task

    @property
    def is_running(self) -> bool:
        """Return whether the AgentLoop background task is still active."""
        return self._agent_task is not None and not self._agent_task.done()

    def _create_provider(self) -> LLMProvider:
        """Build the configured provider without exposing credential values."""
        provider_name = self.config.get_provider_name()
        provider_config = self.config.get_provider()
        provider_spec = find_by_name(provider_name) if provider_name else None

        if provider_config is None or provider_spec is None:
            raise RuntimeError("No configured LLM provider could be resolved.")

        if provider_spec.backend != "openai_compat":
            raise RuntimeError(
                f"Unsupported configured provider backend: {provider_spec.backend}"
            )

        return OpenAICompatProvider(
            api_key=provider_config.api_key or None,
            api_base=self.config.get_api_base(),
            default_model=self.config.agents.defaults.model,
            extra_headers=provider_config.extra_headers,
        )

    async def start(self) -> None:
        """Start one AgentLoop task, leaving an existing active task intact."""
        async with self._lifecycle_lock:
            if self._agent_task is not None and not self._agent_task.done():
                return

            if self._agent_task is not None:
                completed_task = self._agent_task
                self._agent_task = None

                if not completed_task.cancelled():
                    error = completed_task.exception()
                    if error is not None:
                        raise RuntimeError("AgentLoop stopped unexpectedly.") from error

            self._agent_task = asyncio.create_task(
                self.agent_loop.run(),
                name="insurance-copilot-agent-loop",
            )

    async def stop(self) -> None:
        """Stop and await the AgentLoop task; repeated shutdown is safe."""
        async with self._lifecycle_lock:
            self.agent_loop.stop()
            task = self._agent_task

            if task is None:
                return

            if not task.done():
                task.cancel()

            await asyncio.gather(task, return_exceptions=True)
            self._agent_task = None
