
"""Minimal agent loop for the A1 platform foundation."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Awaitable, Callable

from loguru import logger

from nanobot.agent.context import ContextBuilder
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider


class AgentLoop:
    """Connect the message bus, context builder, and LLM provider."""

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        tool_registry: ToolRegistry | None = None,
        max_tool_iterations: int = 4,
    ):
        if max_tool_iterations < 0:
            raise ValueError("max_tool_iterations must not be negative.")

        self.bus = bus
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.tool_registry = tool_registry or ToolRegistry()
        self.max_tool_iterations = max_tool_iterations

        self.context = ContextBuilder(workspace)

        self._running = False
        self._active_tasks: set[asyncio.Task] = set()

    async def run(self) -> None:
        """Consume inbound messages and dispatch them for processing."""
        if self._running:
            raise RuntimeError("Agent loop is already running.")

        self._running = True
        logger.info("Agent loop started")

        try:
            while self._running:
                try:
                    msg = await asyncio.wait_for(
                        self.bus.consume_inbound(),
                        timeout=1.0,
                    )
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning(
                        "Error consuming inbound message: {}",
                        exc,
                    )
                    continue

                if not self._running:
                    break

                task = asyncio.create_task(self._dispatch(msg))
                self._active_tasks.add(task)
                task.add_done_callback(self._active_tasks.discard)

        except asyncio.CancelledError:
            for task in self._active_tasks:
                task.cancel()

            if self._active_tasks:
                await asyncio.gather(
                    *self._active_tasks,
                    return_exceptions=True,
                )

            raise
        finally:
            self._running = False
            logger.info("Agent loop stopped")

    def stop(self) -> None:
        """Stop consuming new messages."""
        self._running = False

    async def _dispatch(self, msg: InboundMessage) -> None:
        """Process one inbound message and publish its response."""
        try:
            response = await self._process_message(msg)

            if response is not None:
                await self.bus.publish_outbound(response)

        except asyncio.CancelledError:
            logger.info(
                "Message processing cancelled: {}",
                msg.session_key,
            )
            raise

        except Exception:
            logger.exception(
                "Error processing message: {}",
                msg.session_key,
            )

            await self.bus.publish_outbound(
                OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content="Sorry, I encountered an error.",
                )
            )

    async def _process_message(
        self,
        msg: InboundMessage,
    ) -> OutboundMessage:
        """Process a single text message using the LLM provider."""

        if msg.media:
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content="Media messages are not supported in A1.",
            )

        messages = self.context.build_messages(
            history=[],
            current_message=msg.content,
            channel=msg.channel,
            chat_id=msg.chat_id,
        )

        tool_definitions = self.tool_registry.get_definitions() or None
        tool_iterations = 0

        while True:
            response = await self.provider.chat_with_retry(
                messages=messages,
                tools=tool_definitions,
                model=self.model,
            )

            if not response.has_tool_calls:
                break

            if tool_iterations >= self.max_tool_iterations:
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=(
                        "Sorry, I couldn't complete the requested tool operations."
                    ),
                    metadata=dict(msg.metadata or {}),
                )

            self.context.add_assistant_message(
                messages,
                response.content,
                tool_calls=[
                    tool_call.to_openai_tool_call()
                    for tool_call in response.tool_calls
                ],
                reasoning_content=response.reasoning_content,
                thinking_blocks=response.thinking_blocks,
            )
            for tool_call in response.tool_calls:
                result = await self.tool_registry.execute(
                    tool_call.name,
                    tool_call.arguments,
                )
                self.context.add_tool_result(
                    messages,
                    tool_call.id,
                    tool_call.name,
                    result,
                )

            tool_iterations += 1

        if response.finish_reason == "error":
            final_content = (
                response.content
                or "Sorry, I encountered an error calling the AI model."
            )

        else:
            final_content = (
                response.content
                or "I've completed processing but have no response to give."
            )

            if response.content:
                self.context.add_assistant_message(
                    messages,
                    response.content,
                    reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )

        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=final_content,
            metadata=dict(msg.metadata or {}),
        )

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        on_stream: Callable[[str], Awaitable[None]] | None = None,
        on_stream_end: Callable[..., Awaitable[None]] | None = None,
    ) -> OutboundMessage:
        """Process a text message directly without using the message bus."""

        if any(
            callback is not None
            for callback in (on_progress, on_stream, on_stream_end)
        ):
            raise NotImplementedError(
                "Progress and streaming callbacks are not supported in A1."
            )

        # Reserved for future session management.
        _ = session_key

        msg = InboundMessage(
            channel=channel,
            sender_id="user",
            chat_id=chat_id,
            content=content,
        )

        return await self._process_message(msg)
