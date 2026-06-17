from __future__ import annotations

import uuid

from sqlalchemy import Column, String, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from config.database import Base


class ChannelRoute(Base):
    __tablename__ = "channel_routes"
    __table_args__ = (
        UniqueConstraint("platform", "channel_identifier", name="uq_platform_channel"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    platform = Column(String(20), nullable=False)  # 'telegram', 'whatsapp', 'web'
    channel_identifier = Column(
        String(255), nullable=False
    )  # bot_token, phone_id, subdomain
    created_at = Column(DateTime, server_default=func.now())
