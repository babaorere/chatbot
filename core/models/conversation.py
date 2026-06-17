from __future__ import annotations

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from config.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())
    state = Column(String, default="CHAT_LIBRE", nullable=False)
    version = Column(Integer, default=0, nullable=False)

    user = relationship("User", backref="conversations")
    messages = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan"
    )

    def transition_to(self, new_state: str) -> None:
        """
        Transición controlada de la máquina de estados.
        Incrementa la versión atómicamente para invalidar botones antiguos.
        """
        if self.state == new_state:
            return

        valid_transitions = {
            "CHAT_LIBRE": ["CHECKOUT_BLOQUEADO", "ESPERANDO_HUMANO"],
            "CHECKOUT_BLOQUEADO": ["CHAT_LIBRE", "ESPERANDO_HUMANO"],
            "ESPERANDO_HUMANO": [
                "HUMANO_ATENDIENDO",
                "POSPUESTA",
                "CANCELADA",
                "CHAT_LIBRE",
            ],
            "HUMANO_ATENDIENDO": [
                "CHAT_LIBRE",
                "POSPUESTA",
                "CANCELADA",
                "ESPERANDO_HUMANO",
            ],
            "POSPUESTA": [
                "HUMANO_ATENDIENDO",
                "CHAT_LIBRE",
                "CANCELADA",
                "ESPERANDO_HUMANO",
            ],
            "CANCELADA": ["ESPERANDO_HUMANO", "CHAT_LIBRE", "HUMANO_ATENDIENDO"],
        }

        if new_state not in valid_transitions.get(self.state, []):
            raise ValueError(
                f"Transición de estado inválida: {self.state} -> {new_state}"
            )

        self.state = new_state
        if self.version is None:
            self.version = 0
        self.version += 1
