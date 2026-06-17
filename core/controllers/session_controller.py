from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from config.database import get_db, set_tenant_context
from services import TenantService, LLMService, ConversationService
from dtos.response import SessionHistoryItem, ConversationResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sessions"])


def resolve_tenant(request: Request, db: Session):
    tenant_id_header = request.headers.get("X-Tenant-ID")
    if not tenant_id_header:
        logger.warning("Missing X-Tenant-ID header on request: %s", request.url.path)
        raise HTTPException(401, "Missing X-Tenant-ID header")

    try:
        tenant_id = uuid.UUID(tenant_id_header)
    except ValueError as e:
        logger.warning(
            "Invalid X-Tenant-ID header format: %s — %s", tenant_id_header, e
        )
        raise HTTPException(401, "Invalid X-Tenant-ID format") from e

    tenant_service = TenantService(db)
    tenant = tenant_service.get_tenant_by_id(tenant_id)
    if not tenant:
        logger.warning("Tenant not found or inactive: %s", tenant_id)
        raise HTTPException(403, f"Tenant {tenant_id} not found or inactive")

    return tenant


@router.get("/sessions/{session_id}/history", response_model=list[SessionHistoryItem])
async def get_session_history(
    session_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    llm: LLMService = Depends(lambda: None),
    fastapi_request: Request = None,
) -> list[SessionHistoryItem]:
    try:
        if not fastapi_request:
            logger.warning("get_session_history called without request context")
            raise HTTPException(401, "Missing X-Tenant-ID header")

        tenant = resolve_tenant(fastapi_request, db)
        set_tenant_context(db, str(tenant.id))
        history = await llm.get_session_history(
            tenant=tenant,
            user_id=user_id,
            session_id=session_id,
        )
        return [SessionHistoryItem(**h) for h in history]
    except HTTPException:
        raise
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
        raise


@router.get("/users/{user_id}/conversations", response_model=list[ConversationResponse])
def list_conversations(
    user_id: int,
    db: Session = Depends(get_db),
    fastapi_request: Request = None,
) -> list[ConversationResponse]:
    try:
        if not fastapi_request:
            logger.warning("list_conversations called without request context")
            raise HTTPException(401, "Missing X-Tenant-ID header")

        tenant = resolve_tenant(fastapi_request, db)
        set_tenant_context(db, str(tenant.id))
        conv_svc = ConversationService(db, tenant.id)
        conversations = conv_svc.get_by_user_id(user_id)
        return [ConversationResponse.model_validate(c) for c in conversations]
    except HTTPException:
        raise
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
        raise
