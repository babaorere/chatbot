from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.container import get_process_message_uc
from controllers import telegram_controller
from controllers.telegram_controller import CatalogSnapshot
from infrastructure.channels.telegram_fsm import (
    ExpectedInput,
    FSMStateStore,
    TelegramConversationFSM,
)
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


@pytest.mark.asyncio
async def test_reply_markup_cleanup_enqueues_serializable_job_payload() -> None:
    with patch("controllers.telegram_controller.JobDispatcher") as dispatcher_mock:
        dispatcher_instance = MagicMock()
        dispatcher_instance.enqueue_job = AsyncMock(return_value={"job_id": "job-1"})
        dispatcher_mock.return_value = dispatcher_instance

        await telegram_controller._defer_clear_reply_markup(
            token="token",
            chat_id=123,
            message_id=456,
            trace_id="tg:test:cleanup",
            user_id="72004",
        )

    dispatcher_instance.enqueue_job.assert_awaited_once()
    assert dispatcher_instance.enqueue_job.call_args.args == ("job_clear_reply_markup",)
    kwargs = dispatcher_instance.enqueue_job.call_args.kwargs
    assert kwargs["token"] == "token"
    assert kwargs["chat_id"] == 123
    assert kwargs["message_id"] == 456
    assert kwargs["trace_id"] == "tg:test:cleanup"
    assert kwargs["user_id"] == "72004"
    assert isinstance(kwargs["event_id"], str)
    assert kwargs["_job_id"].startswith("telegram:clear-reply-markup:")
    assert _is_plain_serializable_payload(
        {key: value for key, value in kwargs.items() if not key.startswith("_")}
    )


@pytest.mark.asyncio
async def test_callback_ack_does_not_wait_for_reply_markup_cleanup() -> None:
    store = FSMStateStore()
    user_id = "72005"
    fsm = TelegramConversationFSM(user_id, store)
    await fsm.persist_menu_metadata(
        version=2,
        options=["menu:promociones"],
        active_menu_id=500,
        menu_scope="menu:main",
        menu_stack=["menu:main"],
        expected_input=ExpectedInput.MENU_SELECTION,
        allow_numeric_input=True,
    )
    cleanup_started = asyncio.Event()
    release_cleanup = asyncio.Event()

    async def slow_cleanup(**_: object) -> None:
        cleanup_started.set()
        await release_cleanup.wait()

    with (
        patch("controllers.telegram_controller.get_fsm_store", return_value=store),
        patch(
            "controllers.telegram_controller.answer_telegram_callback_query",
            new_callable=AsyncMock,
        ) as answer_mock,
        patch(
            "controllers.telegram_controller._defer_clear_reply_markup",
            side_effect=slow_cleanup,
        ),
        patch(
            "controllers.telegram_controller.send_telegram_message",
            new_callable=AsyncMock,
        ) as send_mock,
        patch(
            "controllers.telegram_controller._get_promotions_text",
            return_value=("Promos sin esperar cleanup", []),
        ),
    ):
        send_mock.return_value = 501
        await telegram_controller._process_telegram_update_core(
            token="token",
            chat_id=123,
            user_id=user_id,
            message_obj=None,
            callback_query={
                "id": "callback-1",
                "from": {"id": int(user_id)},
                "message": {
                    "message_id": 500,
                    "chat": {"id": 123},
                    "date": 100000,
                },
                "data": "menu:promociones#2",
            },
            callback_query_id="callback-1",
            msg_obj=None,
            process_message_uc=AsyncMock(),
            trace_id="tg:72005:1",
        )
        await asyncio.wait_for(cleanup_started.wait(), timeout=1)

        answer_mock.assert_awaited_once()
        send_mock.assert_awaited_once()
        release_cleanup.set()
        await asyncio.sleep(0)


def _is_plain_serializable_payload(value: object) -> bool:
    if value is None or isinstance(value, str | int | float | bool):
        return True
    if isinstance(value, list):
        return all(_is_plain_serializable_payload(item) for item in value)
    if isinstance(value, Mapping):
        return all(
            isinstance(key, str) and _is_plain_serializable_payload(item)
            for key, item in value.items()
        )
    return False


@pytest.mark.asyncio
async def test_callback_ack_succeeds_even_when_reply_markup_cleanup_raises_exception() -> None:
    """Verifica que un fallo de encolado ARQ/Redis no bloquea el ack del callback."""
    store = FSMStateStore()
    user_id = "72006"
    fsm = TelegramConversationFSM(user_id, store)
    await fsm.persist_menu_metadata(
        version=2,
        options=["menu:promociones"],
        active_menu_id=500,
        menu_scope="menu:main",
        menu_stack=["menu:main"],
        expected_input=ExpectedInput.MENU_SELECTION,
        allow_numeric_input=True,
    )

    with (
        patch("controllers.telegram_controller.get_fsm_store", return_value=store),
        patch(
            "controllers.telegram_controller.answer_telegram_callback_query",
            new_callable=AsyncMock,
        ) as answer_mock,
        patch("controllers.telegram_controller.JobDispatcher") as dispatcher_mock,
        patch(
            "controllers.telegram_controller.send_telegram_message",
            new_callable=AsyncMock,
        ) as send_mock,
        patch(
            "controllers.telegram_controller._get_promotions_text",
            return_value=("Promos", []),
        ),
    ):
        dispatcher_instance = MagicMock()
        dispatcher_instance.enqueue_job = AsyncMock(
            side_effect=RuntimeError("Redis down")
        )
        dispatcher_mock.return_value = dispatcher_instance
        send_mock.return_value = 501

        await telegram_controller._process_telegram_update_core(
            token="token",
            chat_id=123,
            user_id=user_id,
            message_obj=None,
            callback_query={
                "id": "callback-1",
                "from": {"id": int(user_id)},
                "message": {
                    "message_id": 500,
                    "chat": {"id": 123},
                    "date": 100000,
                },
                "data": "menu:promociones#2",
            },
            callback_query_id="callback-1",
            msg_obj=None,
            process_message_uc=AsyncMock(),
            trace_id="tg:72006:1",
        )

        await asyncio.sleep(0.1)

        answer_mock.assert_awaited_once()
        send_mock.assert_awaited_once()
        dispatcher_instance.enqueue_job.assert_awaited_once()
