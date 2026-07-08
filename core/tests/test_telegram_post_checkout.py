from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch
import httpx
import pytest

from app.container import get_process_message_uc
from controllers.telegram_controller import prime_human_agent_cache
from infrastructure.channels.telegram_fsm import (
    FSMState,
    FSMStateStore,
    TelegramConversationFSM,
)
from main import app
from services.order_service import OrderService
from services.product_service import ProductService
from services.user_service import UserService


@pytest.fixture(autouse=True)
def override_use_case():
    mock_uc = AsyncMock()
    mock_uc.execute = AsyncMock()
    app.dependency_overrides[get_process_message_uc] = lambda: mock_uc
    yield mock_uc
    app.dependency_overrides.pop(get_process_message_uc, None)


@pytest.mark.asyncio
async def test_telegram_orders_menu_flow(
    db_session,
    override_use_case,
) -> None:
    store = FSMStateStore()
    user_id = "80085"
    fsm = TelegramConversationFSM(user_id, store)
    prime_human_agent_cache(True)

    # 1. Crear un usuario y un pedido de prueba
    user = UserService(db_session).get_or_create(
        external_id=user_id, platform="telegram"
    )
    product = ProductService(db_session).create_product(
        sku="TEST-BEER",
        name="Test Beer",
        price=1500.0,
        stock=10,
        category="Cervezas",
    )
    db_session.commit()

    # Generar un pedido mediante checkout
    from services.cart_service import CartService

    CartService(db_session).add_to_cart(
        user_id=user.id, product_id=product.id, quantity=2
    )
    db_session.commit()

    order = OrderService(db_session).checkout_cart(user_id=user.id)
    db_session.commit()

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
        ):
            mock_send.return_value = 9001

            # 2. Navegar al menú de pedidos desde el callback
            await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "callback_query": {
                        "id": "cb_pedidos",
                        "from": {"id": int(user_id)},
                        "message": {
                            "message_id": 100,
                            "chat": {"id": int(user_id)},
                            "date": int(time.time()),
                        },
                        "data": "menu:pedidos#1",
                    }
                },
            )

            # Verificar que renderiza el listado de pedidos
            assert mock_send.call_count > 0
            menu_text = mock_send.call_args_list[-1].kwargs["text"]
            assert "Historial de tus pedidos:" in menu_text
            assert str(order.id)[:8] in menu_text

            # 3. Solicitar buscar un pedido
            mock_send.reset_mock()
            await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "callback_query": {
                        "id": "cb_buscar",
                        "from": {"id": int(user_id)},
                        "message": {
                            "message_id": 9001,
                            "chat": {"id": int(user_id)},
                            "date": int(time.time()),
                        },
                        "data": "menu:buscar_pedido_prompt#2",
                    }
                },
            )

            assert await fsm.get_state() == FSMState.AWAITING_ORDER_ID
            assert (
                "Por favor, escribe el ID"
                in mock_send.call_args_list[-1].kwargs["text"]
            )

            # 4. Enviar el ID del pedido
            mock_send.reset_mock()
            await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "message": {
                        "message_id": 200,
                        "from": {"id": int(user_id), "first_name": "TestUser"},
                        "chat": {"id": int(user_id), "type": "private"},
                        "date": int(time.time()),
                        "text": str(order.id)[:6],  # Envío parcial del ID
                    }
                },
            )

            # Debe haber procesado la búsqueda, devuelto el detalle y regresado a IN_MENU
            assert await fsm.get_state() == FSMState.IN_MENU
            results_text = mock_send.call_args_list[-1].kwargs["text"]
            assert "Detalle del Pedido:" in results_text
            assert "Test Beer x2" in results_text
