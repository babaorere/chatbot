from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)

from config.database import Base


class TenantPortalUser(Base):
    __tablename__ = "tenant_portal_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    full_name = Column(String(120), nullable=False)
    role = Column(String(32), nullable=False, default="manager")
    status = Column(String(32), nullable=False, default="active")
    password_hash = Column(String(512), nullable=True)
    auth_version = Column(Integer, nullable=False, default=1)
    mfa_enabled = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    password_set_at = Column(DateTime, nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    disabled_at = Column(DateTime, nullable=True)


class TenantPortalInvite(Base):
    __tablename__ = "tenant_portal_invites"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), nullable=False, index=True)
    full_name = Column(String(120), nullable=True)
    role = Column(String(32), nullable=False, default="manager")
    token_hash = Column(String(128), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    max_attempts = Column(Integer, nullable=False, default=5)
    attempt_count = Column(Integer, nullable=False, default=0)
    created_by_admin_id = Column(
        Integer,
        ForeignKey("system_admins.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    used_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)


class TenantPortalSession(Base):
    __tablename__ = "tenant_portal_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        Integer,
        ForeignKey("tenant_portal_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    refresh_token_hash = Column(String(128), nullable=False, unique=True, index=True)
    user_agent = Column(Text, nullable=True)
    ip_address = Column(String(64), nullable=True)
    issued_at = Column(DateTime, server_default=func.now(), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    last_seen_at = Column(DateTime, nullable=True)
    rotated_from_session_id = Column(
        String(36),
        ForeignKey("tenant_portal_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    revoked_at = Column(DateTime, nullable=True)
