from __future__ import annotations

from typing import Any

from config.settings import settings


class JobDispatcher:
    """Producer facade for durable background jobs."""

    async def enqueue_job(
        self,
        job_name: str,
        /,
        *args: Any,
        _queue_name: str | None = None,
        _job_id: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Enqueue a job when ARQ is enabled.

        Rules enforced by architecture:
        - arguments must be JSON-serializable
        - no DB sessions, clients, services, or ORM objects
        - caller must pass only primitive payloads or plain structures
        """
        if not settings.arq_enabled:
            raise RuntimeError("ARQ is disabled. Set ARQ_ENABLED=true to enqueue jobs.")

        from arq import create_pool
        from arq.connections import RedisSettings

        redis_settings = RedisSettings.from_dsn(settings.redis_url)
        pool = await create_pool(redis_settings)
        try:
            return await pool.enqueue_job(
                job_name,
                *args,
                _queue_name=_queue_name or settings.arq_queue_name,
                _job_id=_job_id,
                **kwargs,
            )
        finally:
            await pool.aclose()
