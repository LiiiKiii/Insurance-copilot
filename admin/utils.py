"""Shared utilities for the administrative data layer."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def now_beijing() -> datetime:
    """Return the current Beijing time as a database-compatible naive value."""
    return datetime.now(BEIJING_TZ).replace(tzinfo=None)


def get_workspace() -> Path:
    """Return the project workspace root."""
    return Path(__file__).resolve().parent.parent
