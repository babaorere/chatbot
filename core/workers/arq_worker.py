from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from arq.connections import RedisSettings

from config.redis import create_redis_client
from config.settings import settings
from jobs.alerts import job_check_llm_latency, job_notify_critical_issue
from jobs.maintenance import build_worker_health_payload, job_healthcheck
from jobs.sessions import job_clear_latest_conversation_session
from jobs.telegram import job_clear_reply_markup

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(levelname)s:%(name)s:%(message)s",
)


async def _heartbeat_loop(ctx: dict[str, Any]) -> None:
    redis_client = ctx["heartbeat_redis"]
    while True:
        payload = build_worker_health_payload(ctx.get("queue_name"))
        await redis_client.set(
            settings.arq_health_check_key,
            json.dumps(payload),
            ex=60,
        )
        await asyncio.sleep(15)


async def startup(ctx: dict[str, Any]) -> None:
    """Initialize lightweight worker context.

    Worker jobs must construct their own DB sessions and service dependencies.
    No request-scoped objects may be injected into ctx.
    """
    ctx["queue_name"] = settings.arq_queue_name
    ctx["heartbeat_redis"] = create_redis_client(settings)
    ctx["heartbeat_task"] = asyncio.create_task(_heartbeat_loop(ctx))
    logger.info("ARQ worker started [queue=%s]", settings.arq_queue_name)


async def shutdown(ctx: dict[str, Any]) -> None:
    heartbeat_task = ctx.get("heartbeat_task")
    if heartbeat_task is not None:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

    heartbeat_redis = ctx.get("heartbeat_redis")
    if heartbeat_redis is not None:
        try:
            await heartbeat_redis.delete(settings.arq_health_check_key)
        finally:
            await heartbeat_redis.aclose()
    logger.info("ARQ worker stopped [queue=%s]", ctx.get("queue_name"))


class WorkerSettings:
    functions = [
        job_healthcheck,
        job_notify_critical_issue,
        job_check_llm_latency,
        job_clear_latest_conversation_session,
        job_clear_reply_markup,
    ]
    on_startup = startup
    on_shutdown = shutdown
    queue_name = settings.arq_queue_name
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    job_timeout = settings.arq_job_timeout_seconds
    max_tries = settings.arq_job_max_tries
    keep_result = settings.arq_job_result_ttl_seconds
