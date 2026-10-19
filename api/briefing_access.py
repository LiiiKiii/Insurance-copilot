"""Mount-time authorization for the existing briefing router.

The M3 handlers use caller-supplied agent IDs and direct message IDs. Keep
their response and business logic intact while enforcing a live JWT principal
before any handler uses those identifiers.
"""

from __future__ import annotations

from fastapi import Request, status

from admin.dependencies import CurrentUser, DB, _error, is_admin_role
from admin.models.inbox import InboxMessage


_PERSONAL_AGENT_ROUTES = frozenset({
    "briefing_today_summary",
    "briefing_today",
    "briefing_regenerate",
    "briefing_acknowledge",
})
_PERSONAL_MESSAGE_ROUTES = frozenset({
    "briefing_message_detail",
    "briefing_message_read",
    "briefing_message_handled",
})
_ADMIN_ROUTES = frozenset({
    "briefing_settings_get",
    "briefing_settings_put",
    "briefing_warmup_now",
    "briefing_admin_list_agents",
    "briefing_admin_list_messages",
    "briefing_admin_create_message",
    "briefing_admin_update_message",
    "briefing_admin_delete_message",
})


async def require_briefing_access(
    request: Request,
    current_user: CurrentUser,
    db: DB,
) -> None:
    """Authorize each declared briefing route, failing closed for new routes."""
    route = request.scope.get("route")
    name = getattr(route, "name", None)

    if name == "ingest_inbox":
        # Ingest can write messages for any tenant; only platform staff may run it.
        if not current_user.is_superadmin:
            raise _error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "Access denied")
        return

    if name in _PERSONAL_MESSAGE_ROUTES:
        message_id = request.path_params.get("message_id")
        message = await db.get(InboxMessage, message_id)
        if (
            message is None
            or message.tenant_id != current_user.tenant_id
            or message.agent_id != current_user.username
        ):
            raise _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Message not found")
        return

    if name in _ADMIN_ROUTES:
        if not is_admin_role(current_user):
            raise _error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "Access denied")
    elif name not in _PERSONAL_AGENT_ROUTES:
        raise _error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "Access denied")

    agent_id = request.query_params.get("agent_id")
    if agent_id is not None and agent_id != current_user.username:
        raise _error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "Agent access denied")
