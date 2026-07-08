from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.container import get_process_message_uc
from controllers import telegram_controller
from controllers.telegram_controller import CatalogSnapshot
from infrastructure.channels.telegram_fsm import FSMStateStore
from main import app


@pytest.fixture(autouse=True)
def override_use_case() -> None:
    mock_uc = AsyncMock()
    mock_uc.execute = AsyncMock()
    app.dependency_overrides[get_process_message_uc] = lambda: mock_uc
    yield
    app.dependency_overrides.pop(get_process_message_uc, None)


@pytest.mark.asyncio
async def test_start_command_responds_when_idle_prewarm_fails() -> None:
    store = FSMStateStore()
    user_id = "72001"

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        with (
            patch("controllers.telegram_controller.get_fsm_store", return_value=store),
            patch(
                "controllers.telegram_controller.settings.telegram_bot_token",
                "fake_token",
            ),
            patch(
                "controllers.telegram_controller.send_telegram_message",
                new_callable=AsyncMock,
            ) as mock_send,
            patch(
                "controllers.telegram_controller._clear_latest_conversation_session",
                new_callable=AsyncMock,
            ),
            patch(
                "controllers.telegram_controller._prewarm_idle_client_cache",
                new_callable=AsyncMock,
                side_effect=RuntimeError("prewarm down"),
            ),
        ):
            mock_send.return_value = 1001
            response = await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "message": {
                        "message_id": 1,
                        "from": {"id": int(user_id), "first_name": "TestUser"},
                        "chat": {"id": int(user_id), "type": "private"},
                        "date": 100000,
                        "text": "/start",
                    }
                },
            )
            await asyncio.sleep(0)

    assert response.status_code == 200
    mock_send.assert_awaited_once()
    assert "Bienvenido" in mock_send.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_idle_prewarm_logs_failure_without_raising(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)

    with (
        patch(
            "controllers.telegram_controller._catalog_snapshot",
            CatalogSnapshot(version=0),
        ),
        patch(
            "controllers.telegram_controller.prime_catalog_cache",
            side_effect=RuntimeError("db down"),
        ) as prime_mock,
    ):
        await telegram_controller._prewarm_idle_client_cache(
            trace_id="tg:test:prewarm",
            user_id="72002",
            reason="test",
        )

    prime_mock.assert_called_once()
    assert "stage=idle_prewarm failed" in caplog.text


@pytest.mark.asyncio
async def test_reply_markup_cleanup_drops_when_semaphore_is_saturated() -> None:
    saturated_semaphore = asyncio.Semaphore(0)

    with (
        patch(
            "controllers.telegram_controller._reply_markup_cleanup_semaphore",
            saturated_semaphore,
        ),
        patch("controllers.telegram_controller.JobDispatcher") as dispatcher_mock,
    ):
        dispatcher_instance = MagicMock()
        dispatcher_instance.enqueue_job = AsyncMock()
        dispatcher_mock.return_value = dispatcher_instance

        await telegram_controller._defer_clear_reply_markup(
            token="token",
            chat_id=123,
            message_id=456,
            trace_id="tg:test:cleanup",
            user_id="72003",
        )

    dispatcher_instance.enqueue_job.assert_not_called()
