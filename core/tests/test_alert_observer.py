from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.alert_service import AlertService
from application.use_cases.process_message import ProcessMessageUseCase
from application.use_cases.commands import ProcessMessageCommand


@pytest.mark.asyncio
async def test_alert_service_skips_notification_when_no_chat_ids():
    db_mock = MagicMock()
    db_mock.query.return_value.all.return_value = []
    # Mock SystemSettingRepository to return None for chat ids
    with patch(
        "services.alert_service.SystemSettingRepository"
    ) as RepoMock, patch(
        "services.alert_service.send_telegram_message"
    ) as send_mock:
        repo_instance = MagicMock()
        repo_instance.get_value.return_value = None
        RepoMock.return_value = repo_instance

        await AlertService.notify_critical_issue(
            db_mock, "Test Title", "Test Details"
        )
        send_mock.assert_not_called()


@pytest.mark.asyncio
async def test_alert_service_sends_notification_to_all_configured_chat_ids():
    db_mock = MagicMock()
    db_mock.query.return_value.all.return_value = []
    with patch(
        "services.alert_service.SystemSettingRepository"
    ) as RepoMock, patch(
        "services.alert_service.send_telegram_message", new_callable=AsyncMock
    ) as send_mock, patch(
        "services.alert_service.settings"
    ) as settings_mock:

        settings_mock.telegram_bot_token = "fake_bot_token"
        repo_instance = MagicMock()
        repo_instance.get_value.return_value = [11111, 22222]
        RepoMock.return_value = repo_instance

        await AlertService.notify_critical_issue(
            db_mock, "Test Title", "Test Details"
        )

        assert send_mock.call_count == 2
        send_mock.assert_any_call(
            "fake_bot_token", 11111, "🚨 *ALERTA CRÍTICA: Test Title*\n\nTest Details\n\n🏷️ *Tipo:* `error`"
        )
        send_mock.assert_any_call(
            "fake_bot_token", 22222, "🚨 *ALERTA CRÍTICA: Test Title*\n\nTest Details\n\n🏷️ *Tipo:* `error`"
        )


@pytest.mark.asyncio
async def test_process_message_alerts_on_llm_latency_exceeded():
    db_mock = MagicMock()
    db_mock.query.return_value.all.return_value = []
    llm_mock = AsyncMock()
    rag_mock = AsyncMock()
    dispatcher_mock = AsyncMock()

    # Stub run_chat to return immediately
    llm_mock.run_chat.return_value = "Hello response"

    # Mock user retrieval and DB execution to bypass RLS setup
    user_mock = MagicMock()
    user_mock.id = 1
    
    # Mock RAG intent classification to skip RAG
    rag_result = MagicMock()
    rag_result.intent = "TRANSACTIONAL"

    cmd = ProcessMessageCommand(
        user_id="user123",
        platform="web",
        message="hello",
        session_id="session123",
    )

    with patch.object(
        ProcessMessageUseCase, "_get_or_create_user", return_value=user_mock
    ), patch.object(
        ProcessMessageUseCase, "_ensure_conversation"
    ), patch(
        "application.use_cases.process_message.RAGPolicyService"
    ) as RAGPolicyMock, patch(
        "time.perf_counter", side_effect=[0.0, 15.0]
    ):  # Simulated 15 seconds latency

        rag_policy_instance = MagicMock()
        rag_policy_instance.classify.return_value = rag_result
        RAGPolicyMock.return_value = rag_policy_instance

        use_case = ProcessMessageUseCase(
            db=db_mock,
            llm_provider=llm_mock,
            rag_provider=rag_mock,
            job_dispatcher=dispatcher_mock,
        )
        await use_case.execute(cmd)

        dispatcher_mock.enqueue_job.assert_called_once()
        assert dispatcher_mock.enqueue_job.call_args.args[0] == "job_check_llm_latency"
        assert dispatcher_mock.enqueue_job.call_args.kwargs["duration"] == 15.0
        assert dispatcher_mock.enqueue_job.call_args.kwargs["user_id"] == "user123"
        assert dispatcher_mock.enqueue_job.call_args.kwargs["session_id"] == "session123"


@pytest.mark.asyncio
async def test_process_message_alerts_on_llm_failure():
    db_mock = MagicMock()
    db_mock.query.return_value.all.return_value = []
    llm_mock = AsyncMock()
    rag_mock = AsyncMock()
    dispatcher_mock = AsyncMock()

    # Stub run_chat to raise an exception
    llm_mock.run_chat.side_effect = RuntimeError("API key invalid")

    user_mock = MagicMock()
    user_mock.id = 1
    
    rag_result = MagicMock()
    rag_result.intent = "TRANSACTIONAL"

    cmd = ProcessMessageCommand(
        user_id="user123",
        platform="web",
        message="hello",
        session_id="session123",
    )

    with patch.object(
        ProcessMessageUseCase, "_get_or_create_user", return_value=user_mock
    ), patch.object(
        ProcessMessageUseCase, "_ensure_conversation"
    ), patch(
        "application.use_cases.process_message.RAGPolicyService"
    ) as RAGPolicyMock, patch(
        "services.alert_service.AlertService.notify_critical_issue",
        new_callable=AsyncMock,
    ) as notify_mock:

        rag_policy_instance = MagicMock()
        rag_policy_instance.classify.return_value = rag_result
        RAGPolicyMock.return_value = rag_policy_instance

        use_case = ProcessMessageUseCase(
            db=db_mock,
            llm_provider=llm_mock,
            rag_provider=rag_mock,
            job_dispatcher=dispatcher_mock,
        )

        with pytest.raises(RuntimeError):
            await use_case.execute(cmd)

        notify_mock.assert_not_called()
        dispatcher_mock.enqueue_job.assert_called_once()
        assert (
            dispatcher_mock.enqueue_job.call_args.args[0]
            == "job_notify_critical_issue"
        )
        assert (
            dispatcher_mock.enqueue_job.call_args.kwargs["title"]
            == "Fallo en la inferencia del LLM"
        )


@pytest.mark.asyncio
async def test_process_message_alerts_on_llm_latency_falls_back_when_queue_disabled():
    db_mock = MagicMock()
    db_mock.query.return_value.all.return_value = []
    llm_mock = AsyncMock()
    rag_mock = AsyncMock()
    dispatcher_mock = AsyncMock()
    dispatcher_mock.enqueue_job.side_effect = RuntimeError("ARQ is disabled")
    llm_mock.run_chat.return_value = "Hello response"

    user_mock = MagicMock()
    user_mock.id = 1
    rag_result = MagicMock()
    rag_result.intent = "TRANSACTIONAL"

    cmd = ProcessMessageCommand(
        user_id="user123",
        platform="web",
        message="hello",
        session_id="session123",
    )

    with patch.object(
        ProcessMessageUseCase, "_get_or_create_user", return_value=user_mock
    ), patch.object(
        ProcessMessageUseCase, "_ensure_conversation"
    ), patch(
        "application.use_cases.process_message.RAGPolicyService"
    ) as RAGPolicyMock, patch(
        "services.alert_service.AlertService.check_llm_latency",
        new_callable=AsyncMock,
    ) as latency_check_mock, patch(
        "time.perf_counter", side_effect=[0.0, 15.0]
    ):
        rag_policy_instance = MagicMock()
        rag_policy_instance.classify.return_value = rag_result
        RAGPolicyMock.return_value = rag_policy_instance

        use_case = ProcessMessageUseCase(
            db=db_mock,
            llm_provider=llm_mock,
            rag_provider=rag_mock,
            job_dispatcher=dispatcher_mock,
        )
        await use_case.execute(cmd)

        latency_check_mock.assert_called_once_with(
            db=db_mock,
            duration=15.0,
            user_id="user123",
            session_id="session123",
        )
