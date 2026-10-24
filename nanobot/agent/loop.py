
"""Minimal agent loop for the A1 platform foundation."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Awaitable, Callable

from loguru import logger

from nanobot.agent.context import ContextBuilder
from nanobot.agent.coursework_demo import (
    CourseworkCandidateError,
    CourseworkCandidateSource,
    CourseworkDemoScope,
    PreparedCoursework,
    recommendation_result,
    requested_coursework_top_k,
    with_requested_coursework_top_k,
)
from nanobot.agent.feasibility_gate import assess_authenticated_feasibility
from nanobot.agent.skills.insurance.check_feasibility import CheckFeasibilitySkill
from nanobot.agent.skills.insurance.registry import SkillRegistry
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider
from nanobot.retrieval import apply_retrieval_mode
from nanobot.retrieval_citations import (
    deduplicate_citations,
    extract_retrieval_citations,
    strip_retrieval_citations,
)


_AGENT_SCOPED_TOOLS = frozenset({
    "get_performance_snapshot",
    "get_competition_status",
    "get_pending_policies",
    "get_attribution_analysis",
    "generate_chase_plan",
    "generate_improvement_advice",
    "prioritize_followups",
})
_SAFE_TOOL_CALL_ID = re.compile(r"[A-Za-z0-9._:-]{1,100}\Z")
_TRUSTED_CANDIDATE_TOOL = "prioritize_followups"
_COURSEWORK_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": _TRUSTED_CANDIDATE_TOOL,
        "description": (
            "Rank my authorized coursework demo follow-ups: which clients or policies to "
            "follow up first, including requests to recommend the top N (e.g. 'top 3', "
            "'推荐前3名'). Supply no arguments; candidate records and scores are prepared "
            "by the server."
        ),
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
}
_COURSEWORK_TOP_K_GUIDANCE = (
    "The user is asking for a ranked Top-N recommendation of who to follow up. "
    f"Call `{_TRUSTED_CANDIDATE_TOOL}` with no arguments to answer it; do not use "
    "improvement-advice tools for this request."
)


class AgentLoop:
    """Connect the message bus, context builder, and LLM provider."""

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        tool_registry: ToolRegistry | None = None,
        supplemental_tool_registry: ToolRegistry | None = None,
        max_tool_iterations: int = 4,
        coursework_source: CourseworkCandidateSource | None = None,
        skill_registry: SkillRegistry | None = None,
    ):
        if max_tool_iterations < 0:
            raise ValueError("max_tool_iterations must not be negative.")

        self.bus = bus
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.tool_registry = tool_registry or ToolRegistry()
        self.supplemental_tool_registry = supplemental_tool_registry
        self.coursework_source = coursework_source or CourseworkCandidateSource()
        self.skill_registry = skill_registry or SkillRegistry()
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
        demo_scope: CourseworkDemoScope | None = None,
        authenticated_agent_id: str | None = None,
    ) -> OutboundMessage:
        """Process a single text message using the LLM provider."""

        if msg.media:
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content="Media messages are not supported in A1.",
            )

        tool_definitions = self.tool_registry.get_definitions()
        if self.supplemental_tool_registry is not None:
            tool_definitions.extend(self.supplemental_tool_registry.get_definitions())

        prepared: PreparedCoursework | None = None
        if (msg.channel == "websocket" and demo_scope is not None
                and demo_scope.agent_id == msg.chat_id
                and self.tool_registry.has(_TRUSTED_CANDIDATE_TOOL)):
            try:
                prepared = self.coursework_source.prepare(demo_scope)
                prepared = with_requested_coursework_top_k(prepared, msg.content)
            except CourseworkCandidateError:
                pass

        if tool_definitions:
            # The model sees a no-argument facade only after server-side scope
            # and candidate validation. Other callers keep the fail-closed path.
            tool_definitions = [
                definition for definition in tool_definitions
                if definition["function"]["name"] != _TRUSTED_CANDIDATE_TOOL
            ]
            if prepared is not None:
                tool_definitions.append(_COURSEWORK_TOOL_SCHEMA)
        tool_definitions = tool_definitions or None
        guidance = ""
        if (msg.channel == "websocket" and authenticated_agent_id
                and authenticated_agent_id == msg.chat_id):
            guidance = self.skill_registry.get_prompt_injection(
                msg.content, {"tool_definitions": tool_definitions},
            )
        if prepared is not None and requested_coursework_top_k(msg.content) is not None:
            # A bare "推荐前3名" otherwise reads as a request for improvement
            # advice; route explicit Top-K requests to the follow-up ranking.
            guidance = "\n\n".join(filter(None, (guidance, _COURSEWORK_TOP_K_GUIDANCE)))
        messages = self.context.build_messages(
            history=[], current_message=msg.content, channel=msg.channel,
            chat_id=msg.chat_id, trusted_skill_guidance=guidance,
        )
        tool_iterations = 0
        tool_events: list[dict[str, str]] = []
        metadata = dict(msg.metadata or {})
        metadata.pop("tool_events", None)
        metadata.pop("structured_result", None)
        structured_result: dict | None = None
        citations: list[dict] = []

        if (msg.channel == "websocket" and authenticated_agent_id
                and authenticated_agent_id == msg.chat_id
                and CheckFeasibilitySkill().match_intent(msg.content)):
            decision = await assess_authenticated_feasibility(
                msg.content, authenticated_agent_id, self.tool_registry,
            )
            # The provider sees the evidence; its unverified wording cannot
            # replace the server's deterministic conclusion.
            messages[0]["content"] = self.context.build_system_prompt(
                trusted_skill_guidance=(
                    "The server has completed the authoritative feasibility check. "
                    "No further tool calls are available for this turn. "
                    + decision.content
                ),
            )
            try:
                await self.provider.chat_with_retry(
                    messages=messages, tools=None, model=self.model,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Feasibility explanation unavailable (%s)", type(exc).__name__)
            return OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id, content=decision.content,
                metadata={
                    **metadata, "citations": [], "tool_events": list(decision.tool_events),
                    "feasibility_decision": {
                        "status": decision.status, "reason": decision.reason,
                        "target_id": decision.target_id,
                    },
                },
            )

        while True:
            response = await self.provider.chat_with_retry(
                messages=messages,
                tools=tool_definitions,
                model=self.model,
            )

            if not response.has_tool_calls:
                break

            untrusted_call = next(
                (call for call in response.tool_calls if call.name == _TRUSTED_CANDIDATE_TOOL),
                None,
            )
            if untrusted_call is not None and (
                prepared is None or untrusted_call.arguments != {}
                or not isinstance(untrusted_call.id, str)
                or not _SAFE_TOOL_CALL_ID.fullmatch(untrusted_call.id)
            ):
                denied_status = "candidate_source_unavailable" if prepared is None else "invalid_parameters"
                event = {
                    "name": _TRUSTED_CANDIDATE_TOOL,
                    "status": denied_status,
                }
                if isinstance(untrusted_call.id, str) and _SAFE_TOOL_CALL_ID.fullmatch(untrusted_call.id):
                    event["tool_call_id"] = untrusted_call.id
                tool_events.append(event)
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=("Verified follow-up candidates are unavailable."
                             if prepared is None else "Invalid follow-up tool request."),
                    metadata={**metadata, "tool_events": tool_events},
                )

            if tool_iterations >= self.max_tool_iterations:
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=(
                        "Sorry, I couldn't complete the requested tool operations."
                    ),
                    metadata={**metadata, "tool_events": tool_events} if tool_events else metadata,
                )

            apply_retrieval_mode(
                response.tool_calls,
                (msg.metadata or {}).get("retrieval_mode"),
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
                registry = (
                    self.supplemental_tool_registry
                    if self.supplemental_tool_registry is not None
                    and self.supplemental_tool_registry.has(tool_call.name)
                    else self.tool_registry
                )
                arguments = dict(tool_call.arguments)
                if tool_call.name == _TRUSTED_CANDIDATE_TOOL and prepared is not None:
                    # The validated v4 horizon result exceeds the general 5k
                    # output budget; isolate this one server-prepared call.
                    coursework_registry = ToolRegistry(
                        timeout_seconds=registry.timeout_seconds,
                        max_result_chars=6500,
                    )
                    coursework_registry.register(registry.get(tool_call.name))
                    result, status = await coursework_registry.execute_with_status(
                        tool_call.name, prepared.payload,
                    )
                    if status == "completed":
                        try:
                            ranking = json.loads(result)
                            structured_result = recommendation_result(prepared, ranking, tool_call.id)
                            ranking["source"] = structured_result["source"]
                            ranking["as_of_date"] = structured_result["as_of_date"]
                            result = json.dumps(ranking, ensure_ascii=False)
                        except (ValueError, TypeError, CourseworkCandidateError):
                            result, status = "Verified follow-up ranking failed.", "execution_failed"
                            structured_result = None
                elif msg.channel == "websocket" and tool_call.name in _AGENT_SCOPED_TOOLS:
                    requested_agent = arguments.get("agent_id")
                    if requested_agent not in (None, msg.chat_id):
                        result = '{"error":"agent_id is not authorized"}'
                        status = "agent_access_denied"
                    else:
                        arguments["agent_id"] = msg.chat_id
                        result, status = await registry.execute_with_status(
                            tool_call.name, arguments,
                        )
                else:
                    result, status = await registry.execute_with_status(
                        tool_call.name, arguments,
                    )
                citations.extend(
                    extract_retrieval_citations(tool_call.name, result)
                )
                self.context.add_tool_result(
                    messages,
                    tool_call.id,
                    tool_call.name,
                    strip_retrieval_citations(tool_call.name, result),
                )
                event = {
                    "name": tool_call.name if registry.has(tool_call.name) else "unknown_tool",
                    "status": status,
                }
                if isinstance(tool_call.id, str) and _SAFE_TOOL_CALL_ID.fullmatch(tool_call.id):
                    event["tool_call_id"] = tool_call.id
                tool_events.append(event)

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

            if structured_result is not None:
                count = len(structured_result["actions"])
                final_content = (
                    "Here is 1 authorized follow-up recommendation. "
                    "Review the ranked action plan for its action and evidence."
                    if count == 1 else
                    f"Here are {count} authorized follow-up recommendations. "
                    "Review the ranked action plan for their actions and evidence."
                )

            if response.content:
                self.context.add_assistant_message(
                    messages,
                    final_content,
                    reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )

        metadata["citations"] = deduplicate_citations(citations)
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=final_content,
            metadata={
                **metadata,
                **({"tool_events": tool_events} if tool_events else {}),
                **({"structured_result": structured_result} if structured_result and response.finish_reason != "error" else {}),
            },
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
        retrieval_mode: str = "keyword",
        demo_scope: CourseworkDemoScope | None = None,
        authenticated_agent_id: str | None = None,
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
            metadata={"retrieval_mode": retrieval_mode},
        )

        return await self._process_message(
            msg, demo_scope=demo_scope, authenticated_agent_id=authenticated_agent_id,
        )
