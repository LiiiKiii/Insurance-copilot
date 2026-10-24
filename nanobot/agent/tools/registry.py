"""Safe, opt-in registration and execution of agent tools."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from nanobot.agent.tools.base import Tool


logger = logging.getLogger(__name__)


class ToolRegistry:
    """Store explicitly registered tools and execute them safely.

    Duplicate tool names are rejected with ``ValueError``.  Tools are never
    discovered or registered automatically, so hosts retain control over the
    capabilities made available to a model.
    """

    _UNKNOWN_TOOL_MESSAGE = "Tool is not available."
    _INVALID_PARAMETERS_MESSAGE = "Tool arguments are invalid."
    _EXECUTION_FAILED_MESSAGE = "Tool execution failed."
    _TIMEOUT_MESSAGE = "Tool execution timed out."
    _EMPTY_RESULT_MESSAGE = "Tool completed without a result."
    _UNSERIALIZABLE_RESULT_MESSAGE = "Tool returned an unsupported result."
    _RESULT_TOO_LARGE_MESSAGE = "Tool result exceeded size limit."

    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        max_result_chars: int = 20000,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        if max_result_chars <= 0:
            raise ValueError("max_result_chars must be positive.")

        self.timeout_seconds = timeout_seconds
        self.max_result_chars = max_result_chars
        self._tools: dict[str, Tool] = {}

    @property
    def tool_names(self) -> tuple[str, ...]:
        """Return registered tool names in registration order."""
        return tuple(self._tools)

    def register(self, tool: Tool) -> None:
        """Register one tool, rejecting duplicate or invalid names."""
        if not isinstance(tool, Tool):
            raise TypeError("tool must implement Tool.")
        if not isinstance(tool.name, str) or not tool.name.strip():
            raise ValueError("tool name must be a non-empty string.")
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> Tool | None:
        """Remove and return a tool, or ``None`` when it is not registered."""
        return self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        """Return a registered tool by name."""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """Return whether a tool name is registered."""
        return name in self._tools

    def get_definitions(self) -> list[dict[str, Any]]:
        """Return OpenAI-compatible function schemas for registered tools."""
        return [tool.to_schema() for tool in self._tools.values()]

    async def execute(self, name: str, params: object) -> str:
        """Validate, execute, and serialize one tool call safely.

        Model-provided arguments are cast and validated against the tool's
        schema before execution.  Errors are intentionally generic so model
        history never receives exception details or sensitive configuration.
        """
        content, _status = await self.execute_with_status(name, params)
        return content

    async def execute_with_status(self, name: str, params: object) -> tuple[str, str]:
        """Return provider-safe content and a status for transport audit records."""
        tool = self.get(name)
        if tool is None:
            return self._UNKNOWN_TOOL_MESSAGE, "unknown_tool"
        if not isinstance(params, dict):
            return self._INVALID_PARAMETERS_MESSAGE, "invalid_parameters"

        try:
            cast_params = tool.cast_params(params)
            errors = tool.validate_params(cast_params)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Tool argument validation failed (%s)", type(exc).__name__)
            return self._INVALID_PARAMETERS_MESSAGE, "invalid_parameters"

        if errors:
            return self._INVALID_PARAMETERS_MESSAGE, "invalid_parameters"

        try:
            result = await asyncio.wait_for(
                tool.execute(**cast_params),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            return self._TIMEOUT_MESSAGE, "timed_out"
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Tool execution failed (%s)", type(exc).__name__)
            return self._EXECUTION_FAILED_MESSAGE, "execution_failed"

        content = self._to_content(result)
        if len(content) > self.max_result_chars:
            return self._RESULT_TOO_LARGE_MESSAGE[: self.max_result_chars], "result_too_large"
        return content, "completed"

    def _to_content(self, result: Any) -> str:
        """Serialize a result before applying the provider output limit."""
        if result is None:
            content = self._EMPTY_RESULT_MESSAGE
        elif isinstance(result, str):
            content = result or self._EMPTY_RESULT_MESSAGE
        else:
            try:
                content = json.dumps(result, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                content = self._UNSERIALIZABLE_RESULT_MESSAGE

        return content
