from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from jobs.sessions import job_clear_latest_conversation_session


@pytest.mark.asyncio
async def test_job_clear_latest_conversation_session_calls_reset_service() -> None:
    with patch(
        "jobs.sessions.clear_latest_conversation_session",
        new_callable=AsyncMock,
    ) as clear_mock:
        clear_mock.return_value = "session-123"

        await job_clear_latest_conversation_session(
            {},
            user_id="5391760292",
            trace_id="tg:5391760292:1",
            reason="start_command",
            event_id="evt-1",
        )

    clear_mock.assert_awaited_once_with("5391760292")
