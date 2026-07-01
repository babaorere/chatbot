from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jobs.alerts import job_check_llm_latency, job_notify_critical_issue


@pytest.mark.asyncio
async def test_job_notify_critical_issue_uses_worker_db_session() -> None:
    db_mock = MagicMock()

    with patch("jobs.alerts.SessionLocal", return_value=db_mock), patch(
        "jobs.alerts.AlertService.notify_critical_issue",
        new_callable=AsyncMock,
    ) as notify_mock:
        await job_notify_critical_issue(
            {},
            title="Test",
            details="Details",
            alert_type="error",
            user_id="u1",
            session_id="s1",
            event_id="evt-1",
        )

    notify_mock.assert_called_once_with(
        db=db_mock,
        title="Test",
        details="Details",
        alert_type="error",
    )
    db_mock.close.assert_called_once()


@pytest.mark.asyncio
async def test_job_check_llm_latency_uses_worker_db_session() -> None:
    db_mock = MagicMock()

    with patch("jobs.alerts.SessionLocal", return_value=db_mock), patch(
        "jobs.alerts.AlertService.check_llm_latency",
        new_callable=AsyncMock,
    ) as latency_mock:
        await job_check_llm_latency(
            {},
            duration=12.5,
            user_id="u1",
            session_id="s1",
            event_id="evt-2",
        )

    latency_mock.assert_called_once_with(
        db=db_mock,
        duration=12.5,
        user_id="u1",
        session_id="s1",
    )
    db_mock.close.assert_called_once()
