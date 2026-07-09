from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import BackgroundTasks, HTTPException
from starlette.requests import Request

from application.use_cases.telegram_webhook import TelegramWebhookUseCase


def _make_request(body: object) -> Request:
    encoded = json.dumps(body).encode("utf-8")

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": encoded, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/telegram/webhook/fake_token",
        "headers": [(b"content-type", b"application/json")],
    }
    return Request(scope, receive)


def _build_use_case(*, local_locks: set[str] | None = None) -> TelegramWebhookUseCase:
    return TelegramWebhookUseCase(
        telegram_bot_token="fake_token",
        get_redis_client=lambda: None,
        answer_callback_query=AsyncMock(),
        process_update_background=AsyncMock(),
        log_timing=MagicMock(),
        local_locks=local_locks or set(),
    )


@pytest.mark.asyncio
async def test_execute_rejects_invalid_token() -> None:
    use_case = _build_use_case()

    with pytest.raises(HTTPException) as exc_info:
        await use_case.execute(
            token="wrong",
            request=_make_request({"message": {"chat": {"id": 1}, "from": {"id": 1}}}),
            process_message_uc=MagicMock(),
            background_tasks=BackgroundTasks(),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_execute_returns_duplicate_when_local_lock_exists() -> None:
    local_locks = {"42"}
    answer_callback_query = AsyncMock()
    process_update_background = AsyncMock()
    use_case = TelegramWebhookUseCase(
        telegram_bot_token="fake_token",
        get_redis_client=lambda: None,
        answer_callback_query=answer_callback_query,
        process_update_background=process_update_background,
        log_timing=MagicMock(),
        local_locks=local_locks,
    )

    result = await use_case.execute(
        token="fake_token",
        request=_make_request(
            {
                "message": {
                    "message_id": 2,
                    "from": {"id": 42},
                    "chat": {"id": 42},
                    "text": "hola",
                }
            }
        ),
        process_message_uc=MagicMock(),
        background_tasks=BackgroundTasks(),
    )

    assert result == {"status": "ok", "detail": "duplicate request blocked"}
    assert process_update_background.await_count == 0
    assert answer_callback_query.await_count == 0


@pytest.mark.asyncio
async def test_execute_schedules_background_processing_for_valid_message() -> None:
    process_update_background = AsyncMock()
    use_case = TelegramWebhookUseCase(
        telegram_bot_token="fake_token",
        get_redis_client=lambda: None,
        answer_callback_query=AsyncMock(),
        process_update_background=process_update_background,
        log_timing=MagicMock(),
        local_locks=set(),
    )

    background_tasks = BackgroundTasks()
    result = await use_case.execute(
        token="fake_token",
        request=_make_request(
            {
                "update_id": 99,
                "message": {
                    "message_id": 1,
                    "from": {"id": 7},
                    "chat": {"id": 7},
                    "text": "hola",
                },
            }
        ),
        process_message_uc=MagicMock(),
        background_tasks=background_tasks,
    )

    assert result == {"status": "ok", "detail": "scheduled"}
    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    assert task.func is process_update_background
    assert task.kwargs["user_id"] == "7"
    assert task.kwargs["trace_id"] == "tg:7:99"
