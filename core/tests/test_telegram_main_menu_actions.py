from __future__ import annotations

import httpx
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.container import get_process_message_uc
from infrastructure.channels.telegram_fsm import FSMStateStore
from main import app


@pytest.fixture(autouse=True)
def override_use_case():
    mock_uc = AsyncMock()
    mock_uc.execute = AsyncMock()
    app.dependency_overrides[get_process_message_uc] = lambda: mock_uc
    yield
    app.dependency_overrides.pop(get_process_message_uc, None)


@pytest.mark.asyncio
async def test_main_menu_promotions_and_cart_callbacks_render_content():
    store = FSMStateStore()
    user_id = "70001"

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
                "controllers.telegram_controller.answer_telegram_callback_query",
                new_callable=AsyncMock,
            ),
            patch(
                "controllers.telegram_controller._defer_clear_reply_markup",
                new_callable=AsyncMock,
            ),
            patch(
                "controllers.telegram_controller._get_promotions_text",
                return_value="Promociones destacadas del momento:\n\n1. Promo A",
            ),
            patch(
                "controllers.telegram_controller._get_cart_text",
                return_value="Tu carrito está vacío.",
            ),
        ):
            mock_send.return_value = 501

            promotions_payload = {
                "callback_query": {
                    "id": "cb_promos",
                    "from": {"id": int(user_id)},
                    "message": {
                        "message_id": 1,
                        "chat": {"id": int(user_id)},
                        "date": int(time.time()),
                    },
                    "data": "menu:promociones",
                }
            }
            response = await client.post("/telegram/webhook/fake_token", json=promotions_payload)
            assert response.status_code == 200

            cart_payload = {
                "callback_query": {
                    "id": "cb_cart",
                    "from": {"id": int(user_id)},
                    "message": {
                        "message_id": 501,
                        "chat": {"id": int(user_id)},
                        "date": int(time.time()),
                    },
                    "data": "menu:carrito",
                }
            }
            response = await client.post("/telegram/webhook/fake_token", json=cart_payload)
            assert response.status_code == 200

    texts = [call.kwargs["text"] for call in mock_send.call_args_list]
    assert "Promociones destacadas del momento:" in texts[0]
    assert "Tu carrito está vacío." in texts[1]
