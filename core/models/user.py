from __future__ import annotations


from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    func,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from config.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    external_id = Column(String, nullable=False, index=True)
    platform = Column(String, nullable=False)
    display_name = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        # Unique per tenant, not global
        UniqueConstraint("tenant_id", "external_id", "platform", name="uq_tenant_user"),
    )
