from __future__ import annotations

from google.adk.sessions import InMemorySessionService
from google.adk.sessions.base_session_service import BaseSessionService
from redis.asyncio import Redis

from config.redis import create_redis_client
from config.settings import Settings, settings
from services.redis_session_service import RedisSessionService


def create_session_service(
    *,
    config: Settings | None = None,
    redis_client: Redis | None = None,
) -> BaseSessionService:
    runtime_settings = config or settings
    if not runtime_settings.use_redis_sessions:
        return InMemorySessionService()

    client = redis_client or create_redis_client(runtime_settings)
    return RedisSessionService(
        client,
        namespace=runtime_settings.redis_namespace,
        session_ttl_seconds=runtime_settings.redis_session_ttl_seconds,
        lock_timeout_seconds=runtime_settings.redis_lock_timeout_seconds,
        lock_blocking_timeout_seconds=runtime_settings.redis_lock_blocking_timeout_seconds,
    )
