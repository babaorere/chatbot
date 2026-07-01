from __future__ import annotations

import pytest

from jobs.maintenance import job_healthcheck
from services.job_dispatcher import JobDispatcher
from config.settings import settings


@pytest.mark.asyncio
async def test_job_dispatcher_raises_when_arq_disabled():
    dispatcher = JobDispatcher()
    previous = settings.arq_enabled
    settings.arq_enabled = False
    try:
        with pytest.raises(RuntimeError, match="ARQ is disabled"):
            await dispatcher.enqueue_job("jobs.maintenance.job_healthcheck")
    finally:
        settings.arq_enabled = previous


@pytest.mark.asyncio
async def test_job_healthcheck_returns_worker_metadata():
    result = await job_healthcheck({"queue_name": "chatbot:jobs"})
    assert result["status"] == "ok"
    assert result["worker"] == "arq"
    assert result["queue_name"] == "chatbot:jobs"
    assert isinstance(result["timestamp"], int)
