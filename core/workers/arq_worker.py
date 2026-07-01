from __future__ import annotations

import logging
from typing import Any

from arq.connections import RedisSettings

from config.settings import settings
from jobs.alerts import job_check_llm_latency, job_notify_critical_issue
from jobs.maintenance import job_healthcheck
from jobs.sessions import job_clear_latest_conversation_session

logger = logging.getLogger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    """Initialize lightweight worker context.

    Worker jobs must construct their own DB sessions and service dependencies.
    No request-scoped objects may be injected into ctx.
    """
    ctx["queue_name"] = settings.arq_queue_name
    logger.info("ARQ worker started [queue=%s]", settings.arq_queue_name)


async def shutdown(ctx: dict[str, Any]) -> None:
    logger.info("ARQ worker stopped [queue=%s]", ctx.get("queue_name"))


class WorkerSettings:
    functions = [
        job_healthcheck,
        job_notify_critical_issue,
        job_check_llm_latency,
        job_clear_latest_conversation_session,
    ]
    on_startup = startup
    on_shutdown = shutdown
    queue_name = settings.arq_queue_name
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    job_timeout = settings.arq_job_timeout_seconds
    max_tries = settings.arq_job_max_tries
    keep_result = settings.arq_job_result_ttl_seconds
