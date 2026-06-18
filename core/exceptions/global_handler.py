from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config_exceptions import BusinessConfigNotFoundError
from .user_exceptions import UserNotFoundError, UserAlreadyExistsError
from .conversation_exceptions import ConversationNotFoundError

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    app.exception_handler(BusinessConfigNotFoundError)(
        business_config_not_found_handler
    )
    app.exception_handler(UserNotFoundError)(user_not_found_handler)
    app.exception_handler(UserAlreadyExistsError)(user_already_exists_handler)
    app.exception_handler(ConversationNotFoundError)(conversation_not_found_handler)
    app.exception_handler(Exception)(global_exception_handler)


async def business_config_not_found_handler(
    request: Request, exc: BusinessConfigNotFoundError
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    logger.warning("Business config not found [request_id=%s]: %s", request_id, exc)
    return JSONResponse(
        status_code=404, content={"error": str(exc), "request_id": request_id}
    )


async def user_not_found_handler(
    request: Request, exc: UserNotFoundError
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    logger.warning("User not found [request_id=%s]: %s", request_id, exc)
    return JSONResponse(
        status_code=404, content={"error": str(exc), "request_id": request_id}
    )


async def user_already_exists_handler(
    request: Request, exc: UserAlreadyExistsError
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    logger.warning("User already exists [request_id=%s]: %s", request_id, exc)
    return JSONResponse(
        status_code=409, content={"error": str(exc), "request_id": request_id}
    )


async def conversation_not_found_handler(
    request: Request, exc: ConversationNotFoundError
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    logger.warning("Conversation not found [request_id=%s]: %s", request_id, exc)
    return JSONResponse(
        status_code=404, content={"error": str(exc), "request_id": request_id}
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception("Unhandled error [request_id=%s]: %s", request_id, exc)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "request_id": request_id},
    )
