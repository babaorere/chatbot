from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from models.conversation import Conversation
from repositories.base import JpaRepository


class ConversationRepository(JpaRepository[Conversation]):
    def __init__(self, db: Session) -> None:
        super().__init__(Conversation, db)

    def find_by_session_id_and_tenant(
        self,
        session_id: str,
        tenant_id: uuid.UUID,
    ) -> Optional[Conversation]:
        return (
            self.db.query(Conversation)
            .filter(
                Conversation.tenant_id == tenant_id,
                Conversation.session_id == session_id,
            )
            .first()
        )

    def find_by_user_id_and_tenant(
        self,
        user_id: int,
        tenant_id: uuid.UUID,
    ) -> list[Conversation]:
        return (
            self.db.query(Conversation)
            .filter(
                Conversation.tenant_id == tenant_id,
                Conversation.user_id == user_id,
            )
            .order_by(Conversation.created_at.desc())
            .all()
        )

    def find_by_session_id(self, session_id: str) -> Optional[Conversation]:
        return (
            self.db.query(Conversation)
            .filter(Conversation.session_id == session_id)
            .first()
        )

    def exists_by_session_id_and_tenant(
        self,
        session_id: str,
        tenant_id: uuid.UUID,
    ) -> bool:
        return (
            self.db.query(Conversation)
            .filter(
                Conversation.tenant_id == tenant_id,
                Conversation.session_id == session_id,
            )
            .first()
            is not None
        )
