from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .tenant_exceptions import (
    TenantNotFoundError,
    TenantInactiveError,
    ChannelRouteNotFoundError,
    TenantResolutionError,
)
from .user_exceptions import UserNotFoundError, UserAlreadyExistsError
from .conversation_exceptions import ConversationNotFoundError

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    app.exception_handler(TenantNotFoundError)(tenant_not_found_handler)
    app.exception_handler(TenantInactiveError)(tenant_inactive_handler)
    app.exception_handler(ChannelRouteNotFoundError)(channel_route_not_found_handler)
    app.exception_handler(TenantResolutionError)(tenant_resolution_handler)
    app.exception_handler(UserNotFoundError)(user_not_found_handler)
    app.exception_handler(UserAlreadyExistsError)(user_already_exists_handler)
    app.exception_handler(ConversationNotFoundError)(conversation_not_found_handler)
    app.exception_handler(Exception)(global_exception_handler)


async def tenant_not_found_handler(
    request: Request, exc: TenantNotFoundError
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    logger.warning("Tenant not found [request_id=%s]: %s", request_id, exc)
    return JSONResponse(
        status_code=404, content={"error": str(exc), "request_id": request_id}
    )


async def tenant_inactive_handler(
    request: Request, exc: TenantInactiveError
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    logger.warning("Tenant inactive [request_id=%s]: %s", request_id, exc)
    return JSONResponse(
        status_code=403, content={"error": str(exc), "request_id": request_id}
    )


async def channel_route_not_found_handler(
    request: Request, exc: ChannelRouteNotFoundError
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    logger.warning("Channel route not found [request_id=%s]: %s", request_id, exc)
    return JSONResponse(
        status_code=404, content={"error": str(exc), "request_id": request_id}
    )


async def tenant_resolution_handler(
    request: Request, exc: TenantResolutionError
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    logger.warning("Tenant resolution failed [request_id=%s]: %s", request_id, exc)
    return JSONResponse(
        status_code=401, content={"error": str(exc), "request_id": request_id}
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
