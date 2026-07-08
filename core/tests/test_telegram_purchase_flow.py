from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
import time

from app.container import get_process_message_uc
from config.value_limits import CART_QUANTITY_MAX
from controllers.telegram_controller import prime_human_agent_cache
from infrastructure.channels.telegram_fsm import (
    FSMState,
    FSMStateStore,
    TelegramConversationFSM,
)
from infrastructure.channels.telegram_purchase_flow import TelegramPurchaseFlow
from main import app
from services.cart_service import CartService
from services.product_service import ProductService
from services.user_service import UserService
from services.order_service import OrderService


def test_telegram_purchase_flow_parse_quantity_accepts_configured_upper_limit() -> None:
    assert TelegramPurchaseFlow.parse_quantity("1") == 1
    assert (
        TelegramPurchaseFlow.parse_quantity(str(CART_QUANTITY_MAX)) == CART_QUANTITY_MAX
    )


def test_telegram_purchase_flow_parse_quantity_rejects_out_of_range_values() -> None:
    assert TelegramPurchaseFlow.parse_quantity("0") is None
    assert TelegramPurchaseFlow.parse_quantity(str(CART_QUANTITY_MAX + 1)) is None
    assert TelegramPurchaseFlow.parse_quantity("quiero 2") is None


@pytest.fixture(autouse=True)
def override_use_case():
    mock_uc = AsyncMock()
    mock_uc.execute = AsyncMock()
    app.dependency_overrides[get_process_message_uc] = lambda: mock_uc
    yield mock_uc
    app.dependency_overrides.pop(get_process_message_uc, None)


@pytest.mark.asyncio
async def test_telegram_purchase_flow_adds_product_to_cart(
    db_session,
    override_use_case,
) -> None:
    store = FSMStateStore()
    user_id = "70055"
    fsm = TelegramConversationFSM(user_id, store)
    prime_human_agent_cache(True)

    product = ProductService(db_session).create_product(
        sku="CERVEZA-IPA-1",
        name="Cerveza IPA",
        price=2990.0,
        stock=20,
        category="Cervezas",
        unit_of_measure="botella",
    )
    db_session.commit()

    send_ids = [1001, 1002, 1003, 1004, 1005, 1006]

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
            mock_send.side_effect = send_ids

            await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "message": {
                        "message_id": 1,
                        "from": {"id": int(user_id), "first_name": "TestUser"},
                        "chat": {"id": int(user_id), "type": "private"},
                        "date": 100000,
                        "text": "/start",
                    }
                },
            )

            await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "callback_query": {
                        "id": "cb_menu_cat",
                        "from": {"id": int(user_id)},
                        "message": {
                            "message_id": 1001,
                            "chat": {"id": int(user_id)},
                            "date": 100001,
                        },
                        "data": "menu:categorias#2",
                    }
                },
            )

            await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "callback_query": {
                        "id": "cb_cat_select",
                        "from": {"id": int(user_id)},
                        "message": {
                            "message_id": 1002,
                            "chat": {"id": int(user_id)},
                            "date": 100002,
                        },
                        "data": "cat_select:cervezas#3",
                    }
                },
            )

            await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "callback_query": {
                        "id": "cb_product",
                        "from": {"id": int(user_id)},
                        "message": {
                            "message_id": 1003,
                            "chat": {"id": int(user_id)},
                            "date": 100003,
                        },
                        "data": f"product_select:{product.id}#4",
                    }
                },
            )

            state = await fsm.get_state()
            assert state == FSMState.AWAITING_QUANTITY

            await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "message": {
                        "message_id": 5,
                        "from": {"id": int(user_id), "first_name": "TestUser"},
                        "chat": {"id": int(user_id), "type": "private"},
                        "date": 100004,
                        "text": "2",
                    }
                },
            )

            assert await fsm.get_state() == FSMState.AWAITING_CONFIRMATION

            await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "callback_query": {
                        "id": "cb_confirm",
                        "from": {"id": int(user_id)},
                        "message": {
                            "message_id": 1005,
                            "chat": {"id": int(user_id)},
                            "date": 100005,
                        },
                        "data": "cart:add_confirm#5",
                    }
                },
            )

    user = UserService(db_session).get_or_create(
        external_id=user_id, platform="telegram"
    )
    cart = CartService(db_session).get_or_create_cart(user.id)
    assert len(cart.items) == 1
    assert cart.items[0].product_id == product.id
    assert cart.items[0].quantity == 2
    assert await fsm.get_state() == FSMState.IN_MENU
    texts = [call.kwargs["text"] for call in mock_send.call_args_list]
    assert any("Agregué 2 x Cerveza IPA al carrito." in text for text in texts)


@pytest.mark.asyncio
async def test_telegram_purchase_flow_invalid_quantity_repeats_prompt(
    db_session,
    override_use_case,
) -> None:
    store = FSMStateStore()
    user_id = "70056"
    fsm = TelegramConversationFSM(user_id, store)

    product = ProductService(db_session).create_product(
        sku="GIN-1",
        name="Gin London Dry",
        price=15990.0,
        stock=10,
        category="Destilados",
        unit_of_measure="botella",
    )
    db_session.commit()

    await fsm.set_state(
        FSMState.AWAITING_QUANTITY,
        {
            "pending_product_id": str(product.id),
            "pending_product_name": product.name,
            "_menu_stack": ["menu:main", "category:destilados"],
            "_menu_scope": "category:destilados",
            "_expected_input": "quantity",
        },
    )

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
        ):
            mock_send.return_value = 2001

            response = await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "message": {
                        "message_id": 7,
                        "from": {"id": int(user_id), "first_name": "TestUser"},
                        "chat": {"id": int(user_id), "type": "private"},
                        "date": 100010,
                        "text": "quiero 1 kilo de carne",
                    }
                },
            )
            assert response.status_code == 200

    assert await fsm.get_state() == FSMState.AWAITING_QUANTITY
    assert "No entendí esa cantidad." in mock_send.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_telegram_cart_checkout_generates_order_and_clears_cart(
    db_session,
    override_use_case,
) -> None:
    store = FSMStateStore()
    user_id = "70057"
    user = UserService(db_session).get_or_create(
        external_id=user_id, platform="telegram"
    )
    product = ProductService(db_session).create_product(
        sku="PISCO-1",
        name="Pisco Reservado",
        price=6500.0,
        stock=10,
        category="Pisco",
        unit_of_measure="botella",
    )
    CartService(db_session).add_to_cart(
        user_id=user.id, product_id=product.id, quantity=3
    )
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
            patch(
                "controllers.telegram_controller._clear_latest_conversation_session",
                new_callable=AsyncMock,
            ),
        ):
            mock_send.side_effect = [3001, 3002, 3003, 3004]

            await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "message": {
                        "message_id": 0,
                        "from": {"id": int(user_id), "first_name": "TestUser"},
                        "chat": {"id": int(user_id), "type": "private"},
                        "date": int(time.time()),
                        "text": "/start",
                    }
                },
            )

            response = await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "callback_query": {
                        "id": "cb_cart",
                        "from": {"id": int(user_id)},
                        "message": {
                            "message_id": 3001,
                            "chat": {"id": int(user_id)},
                            "date": int(time.time()),
                        },
                        "data": "menu:carrito#2",
                    }
                },
            )
            assert response.status_code == 200

            response = await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "callback_query": {
                        "id": "cb_checkout",
                        "from": {"id": int(user_id)},
                        "message": {
                            "message_id": 3002,
                            "chat": {"id": int(user_id)},
                            "date": int(time.time()),
                        },
                        "data": "cart:start_checkout#3",
                    }
                },
            )
            assert response.status_code == 200

            response = await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "callback_query": {
                        "id": "cb_checkout_confirm",
                        "from": {"id": int(user_id)},
                        "message": {
                            "message_id": 3003,
                            "chat": {"id": int(user_id)},
                            "date": int(time.time()),
                        },
                        "data": "checkout:confirm#4",
                    }
                },
            )
            assert response.status_code == 200

    cart = CartService(db_session).get_or_create_cart(user.id)
    assert len(cart.items) == 0
    orders = OrderService(db_session).list_user_orders(user.id)
    assert len(orders) == 1
    assert orders[0].status == "pending"
    db_session.refresh(product)
    assert product.stock == 7
    texts = [call.kwargs["text"] for call in mock_send.call_args_list]
    assert any("Pedido generado." in text for text in texts)


@pytest.mark.asyncio
async def test_telegram_cart_clear_removes_items(
    db_session,
    override_use_case,
) -> None:
    store = FSMStateStore()
    user_id = "70058"
    user = UserService(db_session).get_or_create(
        external_id=user_id, platform="telegram"
    )
    product = ProductService(db_session).create_product(
        sku="RON-1",
        name="Ron Añejo",
        price=8900.0,
        stock=8,
        category="Ron",
        unit_of_measure="botella",
    )
    CartService(db_session).add_to_cart(
        user_id=user.id, product_id=product.id, quantity=1
    )
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
            patch(
                "controllers.telegram_controller._clear_latest_conversation_session",
                new_callable=AsyncMock,
            ),
        ):
            mock_send.side_effect = [4001, 4002, 4003]

            await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "message": {
                        "message_id": 0,
                        "from": {"id": int(user_id), "first_name": "TestUser"},
                        "chat": {"id": int(user_id), "type": "private"},
                        "date": int(time.time()),
                        "text": "/start",
                    }
                },
            )

            await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "callback_query": {
                        "id": "cb_cart",
                        "from": {"id": int(user_id)},
                        "message": {
                            "message_id": 4001,
                            "chat": {"id": int(user_id)},
                            "date": int(time.time()),
                        },
                        "data": "menu:carrito#2",
                    }
                },
            )

            await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "callback_query": {
                        "id": "cb_clear",
                        "from": {"id": int(user_id)},
                        "message": {
                            "message_id": 4002,
                            "chat": {"id": int(user_id)},
                            "date": int(time.time()),
                        },
                        "data": "cart:clear#3",
                    }
                },
            )

    cart = CartService(db_session).get_or_create_cart(user.id)
    assert len(cart.items) == 0
    assert "Vacié tu carrito." in mock_send.call_args_list[-1].kwargs["text"]
