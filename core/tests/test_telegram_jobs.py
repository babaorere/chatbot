from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

from jobs.telegram import job_clear_reply_markup


@pytest.mark.asyncio
async def test_job_clear_reply_markup_calls_telegram_service() -> None:
    with patch(
        "jobs.telegram.clear_telegram_reply_markup",
        new_callable=AsyncMock,
    ) as clear_mock:
        await job_clear_reply_markup(
            {},
            token="bot-token",
            chat_id=12345,
            message_id=678,
            trace_id="tg:1:2",
            user_id="1",
            event_id="evt-1",
        )

    clear_mock.assert_awaited_once_with(
        bot_token="bot-token",
        chat_id=12345,
        message_id=678,
        trace_id="tg:1:2",
    )


@pytest.mark.asyncio
async def test_job_clear_reply_markup_logs_failure_with_traceable_ids(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)

    with patch(
        "jobs.telegram.clear_telegram_reply_markup",
        new_callable=AsyncMock,
        side_effect=RuntimeError("telegram down"),
    ):
        with pytest.raises(RuntimeError, match="telegram down"):
            await job_clear_reply_markup(
                {"job_try": 2},
                token="bot-token",
                chat_id=12345,
                message_id=678,
                trace_id="tg:1:2",
                user_id="1",
                event_id="evt-1",
            )

    assert "ARQ telegram job failed" in caplog.text
    assert "event_id=evt-1" in caplog.text
    assert "trace_id=tg:1:2" in caplog.text
    assert "user_id=1" in caplog.text
    assert "message_id=678" in caplog.text
    assert "retry=2" in caplog.text
