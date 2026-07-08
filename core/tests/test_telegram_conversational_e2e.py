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
from services.product_service import ProductService
from services.user_service import UserService
from services.order_service import OrderService


@pytest.fixture(autouse=True)
def override_use_case():
    mock_uc = AsyncMock()
    mock_uc.execute = AsyncMock()
    app.dependency_overrides[get_process_message_uc] = lambda: mock_uc
    yield mock_uc
    app.dependency_overrides.pop(get_process_message_uc, None)


@pytest.mark.asyncio
async def test_telegram_conversational_purchase_and_cancellation_flow(
    db_session,
    override_use_case,
) -> None:
    """Valida el flujo conversacional simulado de Telegram:

    1. Comandos /start e inicio del flujo.
    2. Navegación al catálogo y selección de un producto.
    3. Flujo transaccional de compra: ingreso de cantidad, confirmación, y generación de orden de compra.
    4. Consulta y posterior cancelación del pedido recién creado.
    """
    store = FSMStateStore()
    user_id = "133742"
    fsm = TelegramConversationFSM(user_id, store)
    prime_human_agent_cache(True)

    # 1. Crear producto y usuario de prueba
    user = UserService(db_session).get_or_create(
        external_id=user_id, platform="telegram"
    )
    from services.category_service import CategoryService

    CategoryService(db_session).create_category(name="Cervezas")
    product = ProductService(db_session).create_product(
        sku="CONVERSATIONAL-BEER",
        name="Cerveza Conversacional",
        price=2000.0,
        stock=20,
        category="Cervezas",
    )
    db_session.commit()
    from controllers.telegram_controller import prime_catalog_cache

    prime_catalog_cache()

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
                "controllers.telegram_controller._clear_latest_conversation_session",
                new_callable=AsyncMock,
            ),
        ):
            mock_send.return_value = 5001

            # --- PASO 1: Inicio con /start ---
            await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "message": {
                        "message_id": 10,
                        "from": {"id": int(user_id), "first_name": "Tester"},
                        "chat": {"id": int(user_id), "type": "private"},
                        "date": int(time.time()),
                        "text": "/start",
                    }
                },
            )
            assert await fsm.get_state() == FSMState.IN_MENU
            welcome_text = mock_send.call_args_list[-1].kwargs["text"]
            assert "Buen Trago" in welcome_text

            # --- PASO 2: Navegar a categorías ---
            mock_send.reset_mock()
            await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "callback_query": {
                        "id": "cb_cat",
                        "from": {"id": int(user_id)},
                        "message": {
                            "message_id": 5001,
                            "chat": {"id": int(user_id)},
                            "date": int(time.time()),
                        },
                        "data": "menu:categorias#2",
                    }
                },
            )
            assert await fsm.get_state() == FSMState.IN_MENU
            cat_text = mock_send.call_args_list[-1].kwargs["text"]
            assert "Selecciona una categoría" in cat_text

            # --- PASO 3: Seleccionar Categoría Cervezas (slug es 'cervezas') ---
            mock_send.reset_mock()
            await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "callback_query": {
                        "id": "cb_select_cat",
                        "from": {"id": int(user_id)},
                        "message": {
                            "message_id": 5001,
                            "chat": {"id": int(user_id)},
                            "date": int(time.time()),
                        },
                        "data": "cat_select:cervezas#3",
                    }
                },
            )
            assert await fsm.get_state() == FSMState.IN_MENU
            detail_text = mock_send.call_args_list[-1].kwargs["text"]
            assert "Cerveza Conversacional" in detail_text

            # --- PASO 4: Seleccionar el producto para iniciar proceso de compra ---
            mock_send.reset_mock()
            await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "callback_query": {
                        "id": "cb_select_prod",
                        "from": {"id": int(user_id)},
                        "message": {
                            "message_id": 5001,
                            "chat": {"id": int(user_id)},
                            "date": int(time.time()),
                        },
                        "data": f"product_select:{product.id}#4",
                    }
                },
            )
            # FSMState cambia a AWAITING_QUANTITY
            assert await fsm.get_state() == FSMState.AWAITING_QUANTITY
            qty_prompt = mock_send.call_args_list[-1].kwargs["text"]
            assert "Cerveza Conversacional" in qty_prompt
            assert "¿Cuántas unidades" in qty_prompt

            # --- PASO 5: Indicar cantidad inválida y luego una cantidad válida (3 unidades) ---
            mock_send.reset_mock()
            await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "message": {
                        "message_id": 11,
                        "from": {"id": int(user_id), "first_name": "Tester"},
                        "chat": {"id": int(user_id), "type": "private"},
                        "date": int(time.time()),
                        "text": "cantidad_invalida",
                    }
                },
            )
            assert await fsm.get_state() == FSMState.AWAITING_QUANTITY
            invalid_qty_msg = mock_send.call_args_list[-1].kwargs["text"]
            assert "No entendí esa cantidad" in invalid_qty_msg

            # Enviar cantidad válida "3"
            mock_send.reset_mock()
            await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "message": {
                        "message_id": 12,
                        "from": {"id": int(user_id), "first_name": "Tester"},
                        "chat": {"id": int(user_id), "type": "private"},
                        "date": int(time.time()),
                        "text": "3",
                    }
                },
            )
            assert await fsm.get_state() == FSMState.AWAITING_CONFIRMATION
            confirm_msg = mock_send.call_args_list[-1].kwargs["text"]
            assert "Agregar 3 x Cerveza Conversacional" in confirm_msg

            # --- PASO 6: Confirmar adición al carrito ("sí") ---
            mock_send.reset_mock()
            await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "message": {
                        "message_id": 13,
                        "from": {"id": int(user_id), "first_name": "Tester"},
                        "chat": {"id": int(user_id), "type": "private"},
                        "date": int(time.time()),
                        "text": "sí",
                    }
                },
            )
            assert await fsm.get_state() == FSMState.IN_MENU
            added_msg = mock_send.call_args_list[-1].kwargs["text"]
            assert "Agregué 3 x Cerveza Conversacional al carrito" in added_msg
            assert "Ahora tienes 3 item(s)" in added_msg

            # --- PASO 7: Iniciar checkout del carrito ---
            mock_send.reset_mock()
            await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "callback_query": {
                        "id": "cb_checkout",
                        "from": {"id": int(user_id)},
                        "message": {
                            "message_id": 5001,
                            "chat": {"id": int(user_id)},
                            "date": int(time.time()),
                        },
                        "data": "cart:start_checkout#5",
                    }
                },
            )
            assert await fsm.get_state() == FSMState.AWAITING_CONFIRMATION
            checkout_prompt = mock_send.call_args_list[-1].kwargs["text"]
            assert (
                "Vas a generar un pedido con los productos de tu carrito"
                in checkout_prompt
            )

            # --- PASO 8: Confirmar checkout ("confirmar") ---
            mock_send.reset_mock()
            await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "callback_query": {
                        "id": "cb_confirm_checkout",
                        "from": {"id": int(user_id)},
                        "message": {
                            "message_id": 5001,
                            "chat": {"id": int(user_id)},
                            "date": int(time.time()),
                        },
                        "data": "checkout:confirm#6",
                    }
                },
            )
            assert await fsm.get_state() == FSMState.IN_MENU
            checkout_done_msg = mock_send.call_args_list[-1].kwargs["text"]
            assert "Pedido generado." in checkout_done_msg

            # --- PASO 9: Ir a Pedidos y verificar existencia del pedido ---
            mock_send.reset_mock()
            await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "callback_query": {
                        "id": "cb_pedidos_final",
                        "from": {"id": int(user_id)},
                        "message": {
                            "message_id": 5001,
                            "chat": {"id": int(user_id)},
                            "date": int(time.time()),
                        },
                        "data": "menu:pedidos#7",
                    }
                },
            )
            orders_menu_msg = mock_send.call_args_list[-1].kwargs["text"]
            assert "Historial de tus pedidos:" in orders_menu_msg

            # Obtener el ID del pedido generado desde la base de datos
            orders = OrderService(db_session).list_user_orders(user.id)
            assert len(orders) == 1
            order_id = orders[0].id

            # --- PASO 10: Solicitar cancelación y confirmar la cancelación del pedido ---
            mock_send.reset_mock()
            await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "callback_query": {
                        "id": "cb_cancelar_prompt",
                        "from": {"id": int(user_id)},
                        "message": {
                            "message_id": 5001,
                            "chat": {"id": int(user_id)},
                            "date": int(time.time()),
                        },
                        "data": "menu:cancelar_pedido_prompt#8",
                    }
                },
            )
            assert await fsm.get_state() == FSMState.AWAITING_ORDER_ID
            cancel_prompt = mock_send.call_args_list[-1].kwargs["text"]
            assert "escribe el ID" in cancel_prompt

            # Enviar el ID del pedido para confirmación de cancelación
            mock_send.reset_mock()
            await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "message": {
                        "message_id": 14,
                        "from": {"id": int(user_id), "first_name": "Tester"},
                        "chat": {"id": int(user_id), "type": "private"},
                        "date": int(time.time()),
                        "text": str(order_id)[:6],  # Envío parcial del ID
                    }
                },
            )
            assert await fsm.get_state() == FSMState.IN_MENU
            cancellation_done_msg = mock_send.call_args_list[-1].kwargs["text"]
            assert "cancelado exitosamente" in cancellation_done_msg
