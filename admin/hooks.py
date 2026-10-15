"""Best-effort Original audit hooks."""
from __future__ import annotations

import logging
import re
import uuid

from admin.db import AsyncSessionFactory
from admin.models.audit import AiAuditLog
from admin.models.flow_log import FlowLog
from admin.models.usage import TokenUsageLog

logger = logging.getLogger(__name__)
_SECRET_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[^\s,;]+"),
    re.compile(r"(?i)\b(api[_-]?key|password|secret|token)\s*[:=]\s*[^\s,;]+"),
    re.compile(r'(?i)(["\'](?:api[_-]?key|password|secret|token)["\']\s*:\s*)["\'][^"\']*["\']'),
)


def _redact(value: str) -> str:
    value = _SECRET_PATTERNS[0].sub("Bearer [REDACTED]", value)
    value = _SECRET_PATTERNS[1].sub(lambda match: f"{match.group(1)}=[REDACTED]", value)
    return _SECRET_PATTERNS[2].sub(lambda match: f'{match.group(1)}"[REDACTED]"', value)


def _failure(operation: str) -> None:
    # Database exceptions can contain credentials or SQL-bound sensitive values.
    logger.warning("Audit persistence failed: %s", operation)


async def log_token_usage(
    model_id: str,
    display_name: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    latency_ms: int = 0,
    session_id: str | None = None,
    tenant_id: str | None = None,
    user_id: str | None = None,
    cost_usd: float = 0.0,
    model_category: str = "chat",
) -> None:
    try:
        async with AsyncSessionFactory() as db:
            db.add(TokenUsageLog(
                id=str(uuid.uuid4()), tenant_id=tenant_id, user_id=user_id,
                session_id=session_id, model_id=model_id,
                model_display_name=display_name or model_id,
                model_category=model_category, prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens, total_tokens=total_tokens,
                cost_usd=cost_usd, latency_ms=latency_ms,
            ))
            await db.commit()
    except Exception:
        _failure("token usage")


async def log_ai_audit(
    session_id: str | None,
    agent_id: str | None,
    user_query: str,
    ai_response: str,
    tools_called: str | None = None,
    model_id: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    has_compliance_issue: bool = False,
    compliance_notes: str | None = None,
    tenant_id: str | None = None,
    user_id: str | None = None,
) -> None:
    try:
        async with AsyncSessionFactory() as db:
            db.add(AiAuditLog(
                id=str(uuid.uuid4()), tenant_id=tenant_id, user_id=user_id,
                session_id=session_id, agent_id=agent_id,
                user_query=_redact(user_query)[:2000], ai_response=_redact(ai_response)[:5000],
                tools_called=_redact(tools_called) if tools_called else tools_called,
                model_id=model_id,
                prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                has_compliance_issue=has_compliance_issue,
                compliance_notes=_redact(compliance_notes) if compliance_notes else None,
            ))
            await db.commit()
    except Exception:
        _failure("AI audit")


async def log_flow_step(
    session_id: str,
    agent_id: str,
    step_index: int,
    step_type: str,
    content: str = "",
    metadata_json: str | None = None,
    latency_ms: int = 0,
) -> None:
    try:
        async with AsyncSessionFactory() as db:
            db.add(FlowLog(
                id=str(uuid.uuid4()), session_id=session_id, agent_id=agent_id,
                step_index=step_index, step_type=step_type,
                content=_redact(content)[:5000],
                metadata_json=_redact(metadata_json) if metadata_json else None,
                latency_ms=latency_ms,
            ))
            await db.commit()
    except Exception:
        _failure("flow step")
