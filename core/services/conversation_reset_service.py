from __future__ import annotations

from config.database import SessionLocal
from config.settings import settings
from infrastructure.llm.adk_provider import ADKLLMProvider
from services.conversation_service import ConversationService
from services.session_service_factory import create_session_service
from services.user_service import UserService


async def clear_latest_conversation_session(user_id: str) -> str:
    """Resuelve y limpia la sesión conversacional más reciente de un usuario."""
    db = SessionLocal()
    try:
        user = UserService(db).get_or_create(external_id=user_id, platform="telegram")
        conversations = ConversationService(db).get_by_user_id(user.id)
        session_id = conversations[0].session_id if conversations else ""
    finally:
        db.close()

    if not session_id:
        return ""

    provider = ADKLLMProvider(session_service=create_session_service(config=settings))
    await provider.clear_session(user_id=user_id, session_id=session_id)
    return session_id
