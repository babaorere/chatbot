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
        cmd = ProcessMessageCommand(
            user_id=request.user_id,
            platform=request.platform,
            message=request.message,
            session_id=request.session_id,
        )

        result = await process_message_uc.execute(cmd)

        return ChatResponse(
            session_id=result.session_id,
            user_id=result.user_id,
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
    raise NotImplementedError(
        "Streaming is not yet implemented in the new architecture."
    )
