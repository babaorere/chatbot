from __future__ import annotations


from sqlalchemy.orm import Session

from models.message import Message
from repositories.base import JpaRepository


class MessageRepository(JpaRepository[Message]):
    def __init__(self, db: Session) -> None:
        super().__init__(Message, db)

    def find_by_conversation_id(
        self,
        conversation_id: int,
    ) -> list[Message]:
        return (
            self.db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
            .all()
        )

    def count_by_conversation_id(self, conversation_id: int) -> int:
        return (
            self.db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .count()
        )
