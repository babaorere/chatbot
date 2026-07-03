from __future__ import annotations

import os

import pytest

from config.settings import settings
from jobs.maintenance import build_worker_health_payload, job_healthcheck
from services.job_dispatcher import JobDispatcher


@pytest.mark.asyncio
async def test_job_dispatcher_creates_job_when_arq_enabled(
    monkeypatch: pytest.MonkeyPatch,
):
    dispatcher = JobDispatcher()
    previous = settings.arq_enabled
    settings.arq_enabled = True

    class DummyPool:
        def __init__(self) -> None:
            self.closed = False
            self.calls: list[tuple] = []

        async def enqueue_job(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return {"job_id": "job-1"}

        async def aclose(self):
            self.closed = True

    dummy_pool = DummyPool()

    class FakeRedisSettings:
        @staticmethod
        def from_dsn(_dsn):
            return object()

    async def _create_pool(_redis_settings):
        return dummy_pool

    monkeypatch.setattr("services.job_dispatcher.create_pool", _create_pool)
    monkeypatch.setattr("services.job_dispatcher.RedisSettings", FakeRedisSettings)

    try:
        result = await dispatcher.enqueue_job("jobs.maintenance.job_healthcheck")

        assert result == {"job_id": "job-1"}
        assert dummy_pool.closed is True
        assert dummy_pool.calls[0][0][0] == "jobs.maintenance.job_healthcheck"
    finally:
        settings.arq_enabled = previous


@pytest.mark.asyncio
async def test_job_dispatcher_raises_when_arq_disabled() -> None:
    dispatcher = JobDispatcher()
    previous = settings.arq_enabled
    settings.arq_enabled = False

    try:
        with pytest.raises(RuntimeError, match="ARQ is disabled"):
            await dispatcher.enqueue_job("jobs.maintenance.job_healthcheck")
    finally:
        settings.arq_enabled = previous


@pytest.mark.asyncio
async def test_job_dispatcher_propagates_pool_creation_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    dispatcher = JobDispatcher()
    previous = settings.arq_enabled
    settings.arq_enabled = True

    class FakeRedisSettings:
        @staticmethod
        def from_dsn(_dsn):
            return object()

    async def _create_pool(_redis_settings):
        raise RuntimeError("pool broken")

    monkeypatch.setattr("services.job_dispatcher.create_pool", _create_pool)
    monkeypatch.setattr("services.job_dispatcher.RedisSettings", FakeRedisSettings)

    try:
        with pytest.raises(RuntimeError, match="pool broken"):
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
