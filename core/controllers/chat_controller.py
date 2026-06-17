from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from app.container import ProcessMessageUCDep
from application.use_cases.commands import ProcessMessageCommand
from dtos.request import ChatRequest
from dtos.response import ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    process_message_uc: ProcessMessageUCDep,
    fastapi_request: Request = None,
) -> ChatResponse:
    try:
        tenant_id_header = fastapi_request.headers.get("X-Tenant-ID") if fastapi_request else None
        
        cmd = ProcessMessageCommand(
            user_id=request.user_id,
            platform=request.platform,
            channel_identifier=tenant_id_header or "rest",
            message=request.message,
            session_id=request.session_id,
        )

        result = await process_message_uc.execute(cmd)

        return ChatResponse(
            session_id=result.session_id,
            user_id=result.user_id,
            tenant_slug=result.tenant_slug,
            response=result.response,
        )
    except Exception as e:
        request_id = (
            getattr(fastapi_request.state, "request_id", "unknown")
            if fastapi_request
            else "unknown"
        )
        logger.error("Chat endpoint failed [request_id=%s]: %s", request_id, e)
        raise

@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    process_message_uc: ProcessMessageUCDep,
    fastapi_request: Request = None,
) -> EventSourceResponse:
    # TODO: Implement stream in ProcessMessageUseCase if needed.
    # For now, we fallback to non-streaming or raise an error.
    raise NotImplementedError("Streaming is not yet implemented in the new architecture.")
