from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from models.conversation import Conversation
from repositories.conversation_repository import ConversationRepository
from exceptions.conversation_exceptions import ConversationNotFoundError

logger = logging.getLogger(__name__)


class ConversationService:
    def __init__(self, db: Session, tenant_id: uuid.UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.repo = ConversationRepository(db)

    def create_for_user(
        self,
        user_id: int,
        session_id: str | None = None,
    ) -> Conversation:
        try:
            sid = session_id or str(uuid.uuid4())
            conversation = Conversation(
                tenant_id=self.tenant_id,
                user_id=user_id,
                session_id=sid,
            )
            return self.repo.save(conversation)
        except Exception as e:
            logger.error(
                "ConversationService.create_for_user failed [user_id=%s, session_id=%s]: %s",
                user_id,
                session_id,
                e,
            )
            raise

    def get_by_session_id(self, session_id: str) -> Conversation | None:
        try:
            return self.repo.find_by_session_id_and_tenant(session_id, self.tenant_id)
        except Exception as e:
            logger.error(
                "ConversationService.get_by_session_id failed [session_id=%s]: %s",
                session_id,
                e,
            )
            raise

    def get_required_by_session_id(self, session_id: str) -> Conversation:
        try:
            conversation = self.get_by_session_id(session_id)
            if not conversation:
                raise ConversationNotFoundError(session_id)
            return conversation
        except Exception as e:
            logger.error(
                "ConversationService.get_required_by_session_id failed [session_id=%s]: %s",
                session_id,
                e,
            )
            raise

    def get_by_user_id(self, user_id: int) -> list[Conversation]:
        try:
            return self.repo.find_by_user_id_and_tenant(user_id, self.tenant_id)
        except Exception as e:
            logger.error(
                "ConversationService.get_by_user_id failed [user_id=%s]: %s",
                user_id,
                e,
            )
            raise
