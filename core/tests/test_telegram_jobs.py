from __future__ import annotations

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
