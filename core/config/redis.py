from __future__ import annotations

from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from config.settings import Settings, settings


def create_redis_client(config: Settings | None = None) -> Redis:
    """Construye un cliente Redis con timeouts, health checks y política de reintentos."""
    runtime_settings = config or settings
    retry = Retry(
        backoff=ExponentialBackoff(base=0.1, cap=1.0),
        retries=runtime_settings.redis_retry_attempts,
    )
    return Redis.from_url(
        runtime_settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        health_check_interval=runtime_settings.redis_health_check_interval,
        socket_timeout=runtime_settings.redis_socket_timeout_seconds,
        socket_connect_timeout=runtime_settings.redis_socket_connect_timeout_seconds,
        max_connections=runtime_settings.redis_max_connections,
        retry=retry,
        retry_on_error=[RedisConnectionError, RedisTimeoutError],
        retry_on_timeout=True,
    )
