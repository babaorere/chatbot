from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException, status

from controllers.chat_controller import chat, chat_stream
from dtos.request import ChatRequest
from dtos.response import ChatResponse
from application.use_cases.commands import ProcessMessageCommand


@pytest.mark.asyncio
async def test_chat_success_returns_response() -> None:
    uc_mock = AsyncMock()
    uc_mock.execute.return_value = MagicMock(
        session_id="preview-123",
        user_id="123",
        response="¡Hola! En qué puedo ayudarte?",
    )

    request_dto = ChatRequest(
        user_id="123",
        platform="web",
        message="Hola bot",
        session_id="preview-123",
    )

    result = await chat(
        request=request_dto,
        process_message_uc=uc_mock,
        fastapi_request=None,
        token_data={"sub": "123"},
    )

    assert isinstance(result, ChatResponse)
    assert result.session_id == "preview-123"
    assert result.user_id == "123"
    assert result.response == "¡Hola! En qué puedo ayudarte?"
    uc_mock.execute.assert_called_once()
    cmd = uc_mock.execute.call_args[0][0]
    assert isinstance(cmd, ProcessMessageCommand)
    assert cmd.user_id == "123"
    assert cmd.message == "Hola bot"
    assert cmd.session_id == "preview-123"


@pytest.mark.asyncio
async def test_chat_raises_403_when_user_id_mismatch() -> None:
    uc_mock = AsyncMock()

    request_dto = ChatRequest(
        user_id="123",
        platform="web",
        message="Hola bot",
        session_id="preview-123",
    )

    with pytest.raises(HTTPException) as exc_info:
        await chat(
            request=request_dto,
            process_message_uc=uc_mock,
            fastapi_request=None,
            token_data={"sub": "999"},  # Mismatched sub
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    uc_mock.execute.assert_not_called()


@pytest.mark.asyncio
async def test_chat_hides_internal_error_details() -> None:
    uc_mock = AsyncMock()
    uc_mock.execute.side_effect = RuntimeError("Database connection lost")

    request_dto = ChatRequest(
        user_id="123",
        platform="web",
        message="Hola bot",
        session_id="preview-123",
    )

    with pytest.raises(HTTPException) as exc_info:
        await chat(
            request=request_dto,
            process_message_uc=uc_mock,
            fastapi_request=None,
            token_data={"sub": "123"},
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to process chat message"


@pytest.mark.asyncio
async def test_chat_stream_raises_not_implemented_error() -> None:
    uc_mock = AsyncMock()
    request_dto = ChatRequest(
        user_id="123",
        platform="web",
        message="Hola bot",
        session_id="preview-123",
    )

    with pytest.raises(NotImplementedError, match="Streaming is not yet implemented"):
        await chat_stream(
            request=request_dto,
            process_message_uc=uc_mock,
            fastapi_request=None,
        )
