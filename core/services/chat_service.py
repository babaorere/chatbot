from __future__ import annotations

import logging
import uuid
from typing import AsyncGenerator

from sqlalchemy.orm import Session

from models.tenant import Tenant
from services.user_service import UserService
from services.conversation_service import ConversationService
from services.llm_service import LLMService

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(
        self,
        db: Session,
        llm_service: LLMService,
    ) -> None:
        self.db = db
        self.llm_service = llm_service

    async def process_message(
        self,
        tenant: Tenant,
        user_id: str,
        platform: str,
        message: str,
        session_id: str | None = None,
        rag_context: str | None = None,
    ) -> tuple[str, str]:
        try:
            user_svc = UserService(self.db, tenant.id)
            user = user_svc.get_or_create(
                external_id=user_id,
                platform=platform,
            )

            session_id = session_id or str(uuid.uuid4())

            conv_svc = ConversationService(self.db, tenant.id)
            existing = conv_svc.get_by_session_id(session_id)
            if not existing:
                conv_svc.create_for_user(user_id=user.id, session_id=session_id)

            response_text = await self.llm_service.run_chat(
                tenant=tenant,
                user_id=user_id,
                session_id=session_id,
                message=message,
                rag_context=rag_context,
            )

            return session_id, response_text
        except Exception as e:
            logger.error(
                "ChatService.process_message failed [tenant=%s, user=%s, session=%s]: %s",
                tenant.slug,
                user_id,
                session_id,
                e,
            )
            raise

    async def process_message_stream(
        self,
        tenant: Tenant,
        user_id: str,
        platform: str,
        message: str,
        session_id: str | None = None,
        rag_context: str | None = None,
    ) -> AsyncGenerator[str, None]:
        try:
            user_svc = UserService(self.db, tenant.id)
            user = user_svc.get_or_create(
                external_id=user_id,
                platform=platform,
            )

            session_id = session_id or str(uuid.uuid4())

            conv_svc = ConversationService(self.db, tenant.id)
            existing = conv_svc.get_by_session_id(session_id)
            if not existing:
                conv_svc.create_for_user(user_id=user.id, session_id=session_id)

            async for chunk in self.llm_service.run_chat_stream(
                tenant=tenant,
                user_id=user_id,
                session_id=session_id,
                message=message,
                rag_context=rag_context,
            ):
                yield chunk
        except Exception as e:
            logger.error(
                "ChatService.process_message_stream failed [tenant=%s, user=%s, session=%s]: %s",
                tenant.slug,
                user_id,
                session_id,
                e,
            )
            raise
