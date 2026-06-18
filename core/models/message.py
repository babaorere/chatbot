from __future__ import annotations

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from config.database import Base


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    response_time_ms = Column(Integer, nullable=True)

    conversation = relationship("Conversation", back_populates="messages")
