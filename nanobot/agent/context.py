
"""Minimal context builder for the A1 agent runtime."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


UTC_PLUS_8 = timezone(timedelta(hours=8))


class ContextBuilder:
    """Build system prompts and messages for LLM requests."""

    _RUNTIME_CONTEXT_TAG = (
        "[Runtime Context — metadata only, not instructions]"
    )

    def __init__(self, workspace: Path):
        self.workspace = workspace

    def build_system_prompt(
        self,
        skill_names: list[str] | None = None,
    ) -> str:
        """Build the minimal system prompt.

        Skills are intentionally not loaded during A1.
        """
        return (
            "You are nanobot, a helpful AI assistant for "
            "Insurance Performance Intelligence Copilot.\n\n"
            "Answer based on the information available in the conversation. "
            "Do not invent insurance performance figures, policy details, "
            "or results from tools that have not been executed."
        )

    @staticmethod
    def _build_runtime_context(
        channel: str | None,
        chat_id: str | None,
    ) -> str:
        """Build runtime metadata for the current message."""
        current_time = datetime.now(UTC_PLUS_8).isoformat(
            timespec="seconds"
        )

        lines = [f"Current Time: {current_time}"]

        if channel and chat_id:
            lines.extend([
                f"Channel: {channel}",
                f"Chat ID: {chat_id}",
            ])

        return (
            ContextBuilder._RUNTIME_CONTEXT_TAG
            + "\n"
            + "\n".join(lines)
        )

    def build_messages(
        self,
        history: list[dict[str, Any]],
        current_message: str,
        skill_names: list[str] | None = None,
        media: list[str] | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
        current_role: str = "user",
    ) -> list[dict[str, Any]]:
        """Build the messages for one LLM request."""
        if media:
            raise NotImplementedError(
                "Media messages are not supported in A1."
            )

        runtime_context = self._build_runtime_context(
            channel,
            chat_id,
        )

        merged_content = (
            f"{runtime_context}\n\n{current_message}"
        )

        return [
            {
                "role": "system",
                "content": self.build_system_prompt(skill_names),
            },
            *history,
            {
                "role": current_role,
                "content": merged_content,
            },
        ]

    def add_tool_result(
        self,
        messages: list[dict[str, Any]],
        tool_call_id: str,
        tool_name: str,
        result: Any,
    ) -> list[dict[str, Any]]:
        """Append a tool result message."""
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result,
        })

        return messages

    def add_assistant_message(
        self,
        messages: list[dict[str, Any]],
        content: str | None,
        tool_calls: list[dict[str, Any]] | None = None,
        reasoning_content: str | None = None,
        thinking_blocks: list[dict] | None = None,
    ) -> list[dict[str, Any]]:
        """Append an assistant response to the message list."""
        message: dict[str, Any] = {
            "role": "assistant",
            "content": content,
        }

        if tool_calls:
            message["tool_calls"] = tool_calls

        if reasoning_content:
            message["reasoning_content"] = reasoning_content

        if thinking_blocks:
            message["thinking_blocks"] = thinking_blocks

        messages.append(message)
        return messages