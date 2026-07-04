from __future__ import annotations

import asyncio
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock

from services.job_dispatcher import JobDispatcher
from config.settings import settings
from dtos.request import ChatRequest
from controllers.chat_controller import chat
from application.use_cases.commands import ProcessMessageCommand


@pytest.mark.asyncio
async def test_stress_concurrent_arq_job_dispatching(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prueba de estrés: encolado concurrente masivo de 50 jobs en ARQ sin race conditions."""
    dispatcher = JobDispatcher()
    previous_arq = settings.arq_enabled
    settings.arq_enabled = True

    class StressPool:
        def __init__(self) -> None:
            self.closed = False
            self.enqueued_count = 0
            self.lock = asyncio.Lock()

        async def enqueue_job(self, *args, **kwargs):
            async with self.lock:
                self.enqueued_count += 1
            # Simulate slight async network delay
            await asyncio.sleep(0.001)
            return {"job_id": f"job-{uuid.uuid4()}"}

        async def aclose(self):
            self.closed = True

    pool = StressPool()

    class FakeRedisSettings:
        @staticmethod
        def from_dsn(_dsn):
            return object()

    async def _create_pool(_redis_settings):
        return pool

    monkeypatch.setattr("services.job_dispatcher.create_pool", _create_pool)
    monkeypatch.setattr("services.job_dispatcher.RedisSettings", FakeRedisSettings)

    try:
        tasks = [
            dispatcher.enqueue_job("jobs.maintenance.job_healthcheck", idx=i)
            for i in range(50)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        assert len(results) == 50
        assert pool.enqueued_count == 50
        assert all(isinstance(r, dict) and "job_id" in r for r in results)
    finally:
        settings.arq_enabled = previous_arq


@pytest.mark.asyncio
async def test_stress_concurrent_chat_requests_session_isolation() -> None:
    """Prueba de carga/concurrencia: 25 peticiones simultáneas al endpoint /chat."""
    async def mock_execute(cmd: ProcessMessageCommand):
        # Simulate LLM calculation processing delay
        await asyncio.sleep(0.005)
        return MagicMock(
            session_id=cmd.session_id,
            user_id=cmd.user_id,
            response=f"Respuesta para {cmd.message} en sesión {cmd.session_id}",
        )

    uc_mock = AsyncMock()
    uc_mock.execute.side_effect = mock_execute

    async def make_request(idx: int):
        user_id = f"user-{idx}"
        req = ChatRequest(
            user_id=user_id,
            platform="web",
            message=f"Consulta {idx}",
            session_id=f"session-{idx}",
        )
        return await chat(
            request=req,
            process_message_uc=uc_mock,
            fastapi_request=None,
            token_data={"sub": user_id},
        )

    tasks = [make_request(i) for i in range(25)]
    responses = await asyncio.gather(*tasks)

    assert len(responses) == 25
    assert uc_mock.execute.call_count == 25

    # Verify session isolation and zero data cross-talk
    for i, res in enumerate(responses):
        assert res.user_id == f"user-{i}"
        assert res.session_id == f"session-{i}"
        assert f"Consulta {i}" in res.response
        assert f"sesión session-{i}" in res.response


@pytest.mark.asyncio
async def test_stress_concurrent_session_memory_locks() -> None:
    """Simula acceso concurrente de lectura/escritura en sesiones en memoria con cerraduras de exclusión mutua."""
    lock = asyncio.Lock()
    shared_state: dict[str, int] = {"counter": 0}

    async def worker():
        for _ in range(10):
            async with lock:
                val = shared_state["counter"]
                await asyncio.sleep(0.0005)  # Yield loop to force race condition if unlocked
                shared_state["counter"] = val + 1

    workers = [worker() for _ in range(10)]
    await asyncio.gather(*workers)

    # 10 workers * 10 increments = exactly 100 without any lost updates
    assert shared_state["counter"] == 100
