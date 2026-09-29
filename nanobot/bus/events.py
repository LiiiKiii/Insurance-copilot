from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


UTC_PLUS_8 = timezone(timedelta(hours=8))


def _now_utc_plus_8() -> datetime:
    """Return the current timezone-aware UTC+8 datetime."""
    return datetime.now(UTC_PLUS_8)


@dataclass
class InboundMessage:
    channel: str
    sender_id: str
    chat_id: str
    content: str
    timestamp: datetime = field(default_factory=_now_utc_plus_8)
    media: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    session_key_override: str | None = None

    @property
    def session_key(self) -> str:
        return self.session_key_override or f"{self.channel}:{self.chat_id}"


@dataclass
class OutboundMessage:
    channel: str
    chat_id: str
    content: str
    reply_to: str | None = None
    media: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)