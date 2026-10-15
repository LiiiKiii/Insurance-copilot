"""HTTP request audit middleware with verified-principal attribution."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid

from starlette.types import ASGIApp, Receive, Scope, Send

from admin.db import get_sync_db
from admin.models.audit import RequestLog

logger = logging.getLogger(__name__)
_TRACKED_PREFIXES = ("/admin/", "/api/")


def _should_track(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _TRACKED_PREFIXES)


def _write_log_sync(
    req_id: str, tenant_id: str | None, user_id: str | None,
    endpoint: str, method: str, status_code: int, latency_ms: int,
    ip_address: str, user_agent: str,
) -> None:
    try:
        with get_sync_db() as db:
            db.add(RequestLog(
                id=req_id, tenant_id=tenant_id, user_id=user_id,
                endpoint=endpoint, method=method, status_code=status_code,
                latency_ms=latency_ms, ip_address=ip_address, user_agent=user_agent,
            ))
    except Exception:
        logger.warning("Audit persistence failed: HTTP request")


class AdminAuditMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not _should_track(scope.get("path", "")):
            await self.app(scope, receive, send)
            return

        started = time.monotonic()
        status_code = 500

        async def send_wrapper(message: dict) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except BaseException:
            status_code = 500
            raise
        finally:
            principal = scope.get("state", {}).get("audit_principal")
            user_id, tenant_id = principal if isinstance(principal, tuple) and len(principal) == 2 else (None, None)
            headers = dict(scope.get("headers", []))
            user_agent = headers.get(b"user-agent", b"").decode("utf-8", errors="replace")[:200]
            client = scope.get("client")
            ip_address = client[0] if client else ""
            args = (
                str(uuid.uuid4()), tenant_id, user_id, scope.get("path", ""),
                scope.get("method", ""), status_code,
                int((time.monotonic() - started) * 1000), ip_address, user_agent,
            )
            try:
                await asyncio.to_thread(_write_log_sync, *args)
            except Exception:
                logger.warning("Audit persistence failed: HTTP request")
