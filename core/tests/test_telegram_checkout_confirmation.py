from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.telegram_service import (
    extract_checkout_customer_message,
    send_checkout_confirmation_message,
)


def test_extract_checkout_customer_message_returns_trimmed_text() -> None:
    payload = {"customer_message": "  Compra confirmada.  "}

    assert extract_checkout_customer_message(payload) == "Compra confirmada."


@pytest.mark.asyncio
async def test_send_checkout_confirmation_message_uses_customer_message() -> None:
    with patch(
        "services.telegram_service.send_telegram_message", new_callable=AsyncMock
    ) as send_mock:
        send_mock.return_value = 321

        result = await send_checkout_confirmation_message(
            bot_token="bot-token",
            chat_id=123,
            checkout_payload={
                "customer_message": "Compra confirmada.\nTiempo estimado de atención: 35 minutos.",
            },
        )

    assert result == 321
    send_mock.assert_awaited_once()
    assert (
        "Tiempo estimado de atención: 35 minutos."
        in send_mock.await_args.kwargs["text"]
    )
