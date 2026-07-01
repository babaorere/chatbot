from __future__ import annotations

import os

import pytest

from config.settings import settings
from jobs.maintenance import build_worker_health_payload, job_healthcheck
from services.job_dispatcher import JobDispatcher


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


def test_build_worker_health_payload_includes_pid():
    result = build_worker_health_payload("chatbot:jobs")
    assert result["status"] == "ok"
    assert result["worker"] == "arq"
    assert result["queue_name"] == "chatbot:jobs"
    assert result["pid"] == os.getpid()
