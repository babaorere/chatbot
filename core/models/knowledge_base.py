from __future__ import annotations

import uuid

from sqlalchemy import Column, String, DateTime, Text, Boolean, func
from sqlalchemy.dialects.postgresql import UUID
from config.database import Base


class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category = Column(String(100), nullable=False)
    title = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "category": self.category,
            "title": self.title,
            "content": self.content,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
