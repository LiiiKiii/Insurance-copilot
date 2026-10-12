"""User, Role, Permission models."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from admin.db import Base
from admin.utils import now_beijing

# Many-to-many association tables
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", String(36), ForeignKey("users.id"), primary_key=True),
    Column("role_id", String(36), ForeignKey("roles.id"), primary_key=True),
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", String(36), ForeignKey("roles.id"), primary_key=True),
    Column("permission_id", String(36), ForeignKey("permissions.id"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)
    tier: Mapped[str] = mapped_column(String(20), default="agent")  # director|team_lead|senior_agent|agent
    supervisor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # FK to users.id (upper)
    daily_call_limit: Mapped[int] = mapped_column(Integer, default=50)  # Zero means unlimited.
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing, onupdate=now_beijing)

    roles: Mapped[list[Role]] = relationship("Role", secondary=user_roles, back_populates="users")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing)

    users: Mapped[list[User]] = relationship("User", secondary=user_roles, back_populates="roles")
    permissions: Mapped[list[Permission]] = relationship(
        "Permission", secondary=role_permissions, back_populates="roles"
    )


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    resource: Mapped[str] = mapped_column(String(100), nullable=False)  # users, knowledge_bases, etc.
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # read, write, delete, admin
    description: Mapped[str] = mapped_column(String(500), default="")

    roles: Mapped[list[Role]] = relationship("Role", secondary=role_permissions, back_populates="permissions")
