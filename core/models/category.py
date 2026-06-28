from __future__ import annotations

from sqlalchemy import Column, String, Boolean, func, DateTime
from config.database import Base


class Category(Base):
    __tablename__ = "categories"

    name = Column(String(100), primary_key=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    is_system = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "slug": self.slug,
            "is_system": self.is_system,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
