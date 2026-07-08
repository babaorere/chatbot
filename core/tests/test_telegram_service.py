from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.telegram_service import (
    answer_telegram_callback_query,
    clear_telegram_reply_markup,
    send_telegram_message,
)


@pytest.mark.asyncio
async def test_send_telegram_message_raises_when_api_reports_failure() -> None:
    client_mock = AsyncMock()
    response_mock = MagicMock()
    response_mock.status_code = 500
    response_mock.json.return_value = {"ok": False}
    response_mock.text = "boom"
    client_mock.post.return_value = response_mock

    with patch("services.telegram_service.get_http_client", return_value=client_mock):
        with pytest.raises(RuntimeError, match="Failed to send Telegram message"):
            await send_telegram_message("bot-token", 123, "hola")


@pytest.mark.asyncio
async def test_clear_telegram_reply_markup_raises_when_api_reports_failure() -> None:
    client_mock = AsyncMock()
    response_mock = MagicMock()
    response_mock.status_code = 500
    response_mock.json.return_value = {"ok": False}
    response_mock.text = "boom"
    client_mock.post.return_value = response_mock

    with patch("services.telegram_service.get_http_client", return_value=client_mock):
        with pytest.raises(RuntimeError, match="Failed to clear Telegram reply markup"):
            await clear_telegram_reply_markup("bot-token", 123, 456)


@pytest.mark.asyncio
async def test_clear_telegram_reply_markup_sends_empty_inline_keyboard() -> None:
    client_mock = AsyncMock()
    response_mock = MagicMock()
    response_mock.status_code = 200
    response_mock.json.return_value = {"ok": True}
    client_mock.post.return_value = response_mock

    with patch("services.telegram_service.get_http_client", return_value=client_mock):
        result = await clear_telegram_reply_markup("bot-token", 123, 456)

    assert result is True
    assert client_mock.post.call_args.kwargs["json"]["reply_markup"] == {
        "inline_keyboard": []
    }


@pytest.mark.asyncio
async def test_answer_telegram_callback_query_raises_when_api_reports_failure() -> None:
    client_mock = AsyncMock()
    response_mock = MagicMock()
    response_mock.status_code = 500
    response_mock.json.return_value = {"ok": False}
    response_mock.text = "boom"
    client_mock.post.return_value = response_mock

    with patch("services.telegram_service.get_http_client", return_value=client_mock):
        with pytest.raises(RuntimeError, match="Failed to answer callback query"):
            await answer_telegram_callback_query("bot-token", "callback-1")


@pytest.mark.asyncio
async def test_send_telegram_message_raises_when_transport_broken() -> None:
    client_mock = AsyncMock()
    client_mock.post.side_effect = RuntimeError("transport broken")

    with patch("services.telegram_service.get_http_client", return_value=client_mock):
        with pytest.raises(RuntimeError, match="Failed to send Telegram message"):
            await send_telegram_message("bot-token", 123, "hola")
