from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

from redis.asyncio import Redis

from config.redis import create_redis_client
from config.settings import Settings, settings

if TYPE_CHECKING:
    from google.adk.sessions.base_session_service import BaseSessionService


def create_session_service(
    *,
    config: Settings | None = None,
    redis_client: Redis | None = None,
) -> "BaseSessionService":
    """Crea el backend de sesiones ADK según la configuración activa de la aplicación."""
    runtime_settings = config or settings
    if not runtime_settings.use_redis_sessions:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                category=DeprecationWarning,
                message="BaseAgentConfig is deprecated and will be removed in future versions\\.",
            )
            from google.adk.sessions import InMemorySessionService

        return InMemorySessionService()

    client = redis_client or create_redis_client(runtime_settings)
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            category=DeprecationWarning,
            message="BaseAgentConfig is deprecated and will be removed in future versions\\.",
        )
        from services.redis_session_service import RedisSessionService

    return RedisSessionService(
        client,
        namespace=runtime_settings.redis_namespace,
        session_ttl_seconds=runtime_settings.redis_session_ttl_seconds,
        lock_timeout_seconds=runtime_settings.redis_lock_timeout_seconds,
        lock_blocking_timeout_seconds=runtime_settings.redis_lock_blocking_timeout_seconds,
    )
