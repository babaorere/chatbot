from __future__ import annotations

import logging
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

from config.settings import settings

logger = logging.getLogger(__name__)

API_KEY_HEADER = APIKeyHeader(name="X-Admin-API-Key", auto_error=False)


async def get_admin_api_key(
    api_key: str | None = Security(API_KEY_HEADER),
) -> str:
    """FastAPI dependency to secure admin endpoints using the X-Admin-API-Key header.

    Checks the incoming header against the configured settings.admin_api_key.
    """
    if not settings.admin_api_key:
        logger.error("ADMIN_API_KEY is not set in settings or .env file.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin API Key is not configured on the server.",
        )
    if not api_key or api_key != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials. Invalid or missing Admin API Key.",
        )
    return api_key
