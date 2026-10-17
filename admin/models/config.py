"""Plaintext, non-secret system configuration records."""
from __future__ import annotations

import re
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, validates

from admin.db import Base
from admin.utils import now_beijing


_SECRET_KEY_PATTERN = re.compile(
    r"(?:^|[._-])(?:api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"password(?:[_-]?hash)?|fernet[_-]?key|encryption[_-]?key|"
    r"private[_-]?key|client[_-]?secret|secret)(?:$|[._-])",
    re.IGNORECASE,
)
_CONFIG_TYPES = frozenset({"string", "int", "float", "json", "bool"})


def is_secret_config_key(key: str) -> bool:
    """Return whether ``key`` names a credential prohibited from this store.

    This intentionally narrow key-name policy is a guardrail for the plaintext
    table, not a claim that arbitrary content can be classified as safe.
    Credentials belong in encrypted credential storage instead.
    """

    return bool(_SECRET_KEY_PATTERN.search(key))


class SystemConfig(Base):
    """A global or tenant-scoped, non-secret configuration value."""

    __tablename__ = "system_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "config_key", name="uq_system_configs_tenant_key"),
        Index(
            "uq_system_configs_global_key",
            "config_key",
            unique=True,
            sqlite_where=text("tenant_id IS NULL"),
            postgresql_where=text("tenant_id IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    config_key: Mapped[str] = mapped_column(String(200), nullable=False)
    config_value: Mapped[str] = mapped_column(Text, nullable=False)
    config_type: Mapped[str] = mapped_column(String(20), default="string", nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing, onupdate=now_beijing)

    @validates("config_key")
    def _validate_config_key(self, _name: str, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Configuration keys must be non-empty strings.")
        if is_secret_config_key(value):
            raise ValueError("Secret-like configuration keys require encrypted credential storage.")
        return value.strip()

    @validates("config_type")
    def _validate_config_type(self, _name: str, value: str) -> str:
        if value not in _CONFIG_TYPES:
            raise ValueError("Unsupported system configuration type.")
        return value
