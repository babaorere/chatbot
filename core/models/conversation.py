from __future__ import annotations

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from config.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())
    state = Column(String, default="CHAT_LIBRE", nullable=False)
    version = Column(Integer, default=0, nullable=False)

    user = relationship("User", backref="conversations")
    messages = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan"
    )

    def transition_to(self, new_state: str) -> None:
        if self.state == new_state:
            return
        allowed = {
            "CHAT_LIBRE": ["AWAITING_PRODUCT", "AWAITING_CONFIRMATION", "CLOSED"],
            "AWAITING_PRODUCT": ["CHAT_LIBRE", "CLOSED"],
            "AWAITING_CONFIRMATION": ["CHAT_LIBRE", "CLOSED"],
            "CLOSED": ["CHAT_LIBRE"],
        }
        if new_state not in allowed.get(self.state, []):
            raise ValueError(f"Invalid transition: {self.state} → {new_state}")
        self.state = new_state
        if self.version is None:
            self.version = 0
        self.version += 1
