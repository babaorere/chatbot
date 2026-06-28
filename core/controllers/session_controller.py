from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from config.database import get_db
from app.container import get_llm_provider
from application.ports.llm_port import ILLMProvider
from services import ConversationService
from dtos.response import SessionHistoryItem, ConversationResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sessions"])


@router.get("/sessions/{session_id}/history", response_model=list[SessionHistoryItem])
async def get_session_history(
    session_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    llm: ILLMProvider = Depends(get_llm_provider),
    fastapi_request: Request = None,
) -> list[SessionHistoryItem]:
    try:
        history = await llm.get_session_history(
            user_id=user_id,
            session_id=session_id,
        )
        return [SessionHistoryItem(**h) for h in history]
    except Exception as e:
        request_id = (
            getattr(fastapi_request.state, "request_id", "unknown")
            if fastapi_request
            else "unknown"
        )
        logger.error(
            "get_session_history failed [request_id=%s, session_id=%s]: %s",
            request_id,
            session_id,
            e,
        )
        raise HTTPException(500, f"Failed to retrieve session history: {e}")


@router.get("/users/{user_id}/conversations", response_model=list[ConversationResponse])
def list_conversations(
    user_id: int,
    db: Session = Depends(get_db),
    fastapi_request: Request = None,
) -> list[ConversationResponse]:
    try:
        from sqlalchemy import text
        db.execute(text("SET app.current_user_id = :user_id"), {"user_id": user_id})
        conv_svc = ConversationService(db)
        conversations = conv_svc.get_by_user_id(user_id)
        return [ConversationResponse.model_validate(c) for c in conversations]
    except Exception as e:
        request_id = (
            getattr(fastapi_request.state, "request_id", "unknown")
            if fastapi_request
            else "unknown"
        )
        logger.error(
            "list_conversations failed [request_id=%s, user_id=%s]: %s",
            request_id,
            user_id,
            e,
        )
        raise HTTPException(500, f"Failed to list conversations: {e}")
