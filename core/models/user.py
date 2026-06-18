from __future__ import annotations

from sqlalchemy import Column, Integer, String, DateTime, func, UniqueConstraint
from config.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, nullable=False, index=True)
    platform = Column(String, nullable=False)
    display_name = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("external_id", "platform", name="uq_user_platform"),
    )
