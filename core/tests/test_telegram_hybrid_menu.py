import pytest
import httpx
from unittest.mock import patch, AsyncMock, MagicMock
from main import app
from app.container import get_process_message_uc
from infrastructure.channels.telegram_fsm import (
    FSMState,
    FSMStateStore,
    TelegramConversationFSM,
)
from controllers.telegram_controller import prime_human_agent_cache


@pytest.fixture(autouse=True)
def mock_use_case():
    """Fixture para aislar el caso de uso y evitar polución de dependencias entre tests."""
    mock_uc = MagicMock()
    mock_uc.execute = AsyncMock()
    mock_uc.clear_session = AsyncMock()

    app.dependency_overrides[get_process_message_uc] = lambda: mock_uc
    yield mock_uc
    app.dependency_overrides.pop(get_process_message_uc, None)


@pytest.mark.asyncio
async def test_telegram_hybrid_menu_flow(mock_use_case):
    """Prueba que el usuario pueda seleccionar opciones de menú enviando el número por chat."""
    store = FSMStateStore()
    user_id = "5391760292"
    fsm = TelegramConversationFSM(user_id, store)
    prime_human_agent_cache(True)

    # 1. Parcheamos el envío a Telegram y la persistencia del FSM
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
                "services.telegram_service.answer_telegram_callback_query",
                new_callable=AsyncMock,
            ),
            patch(
                "services.telegram_service.clear_telegram_reply_markup",
                new_callable=AsyncMock,
            ),
            patch(
                "controllers.telegram_controller._clear_latest_conversation_session",
                new_callable=AsyncMock,
            ) as mock_clear_latest_session,
            patch(
                "controllers.telegram_controller._defer_clear_reply_markup",
                new_callable=AsyncMock,
            ) as mock_defer_clear_reply_markup,
        ):
            mock_send.return_value = 1001

            # Enviar /start para limpiar sesión y presentar el menú principal
            payload_start = {
                "message": {
                    "message_id": 1,
                    "from": {"id": int(user_id), "first_name": "TestUser"},
                    "chat": {"id": int(user_id), "type": "private"},
                    "date": 100000,
                    "text": "/start",
                }
            }
            resp = await client.post("/telegram/webhook/fake_token", json=payload_start)
            assert resp.status_code == 200
            mock_use_case.execute.assert_not_awaited()
            mock_use_case.clear_session.assert_not_awaited()
            mock_clear_latest_session.assert_awaited_once()
            mock_defer_clear_reply_markup.assert_not_called()

            # El FSM debe haber guardado las opciones del menú principal en el contexto
            ctx = await fsm.get_context()
            assert "_menu_options" in ctx
            assert ctx["_menu_options"] == [
                "menu:categorias",
                "menu:promociones",
                "menu:mas_vendidos",
                "menu:carrito",
                "menu:pedidos",
                "menu:horario",
            ]

            # 2. Enviar la opción "1" como mensaje de texto para ir a Categorías
            payload_option_1 = {
                "message": {
                    "message_id": 2,
                    "from": {"id": int(user_id), "first_name": "TestUser"},
                    "chat": {"id": int(user_id), "type": "private"},
                    "date": 100005,
                    "text": "1",
                }
            }

            # Parchear listado de categorías en base de datos para simular retorno
            from controllers.telegram_controller import _categories_cache, _products_by_category_cache
            _categories_cache.clear()
            _categories_cache.append({"name": "General", "slug": "general", "is_system": True})
            _products_by_category_cache.clear()
            
            resp2 = await client.post(
                "/telegram/webhook/fake_token", json=payload_option_1
            )
            assert resp2.status_code == 200

            # Debe haber enviado el listado de categorías a Telegram (con versión incrementada a 3)
            category_call = next(
                call
                for call in mock_send.call_args_list
                if call.kwargs.get("text")
                == "Selecciona una categoría."
            )
            assert category_call.kwargs["bot_token"] == "fake_token"
            assert category_call.kwargs["chat_id"] == int(user_id)
            assert category_call.kwargs["reply_markup"] == {
                "inline_keyboard": [
                    [
                        {"text": "1. 🏷️ General", "callback_data": "cat_select:general#3"}
                    ],
                    [
                        {"text": "V. ↩️ Volver", "callback_data": "menu:back#3"},
                        {"text": "M. 🏠 Menú principal", "callback_data": "menu:home#3"},
                    ],
                ]
            }

            # 3. Enviar la opción "v" para volver al menú principal desde el menú de categorías
            payload_option_2 = {
                "message": {
                    "message_id": 3,
                    "from": {"id": int(user_id), "first_name": "TestUser"},
                    "chat": {"id": int(user_id), "type": "private"},
                    "date": 100010,
                    "text": "v",
                }
            }
            resp3 = await client.post(
                "/telegram/webhook/fake_token", json=payload_option_2
            )
            assert resp3.status_code == 200

            # Debe haber vuelto a enviar el menú principal (con versión incrementada a 4)
            back_to_main_call = next(
                call
                for call in mock_send.call_args_list
                if call.kwargs.get("text") == "¿En qué puedo ayudarte hoy?"
            )
            assert back_to_main_call.kwargs["bot_token"] == "fake_token"
            assert back_to_main_call.kwargs["chat_id"] == int(user_id)
            assert back_to_main_call.kwargs["reply_markup"] == {
                "inline_keyboard": [
                    [
                        {"text": "1. 🛍️ Ver Catálogo", "callback_data": "menu:categorias#4"},
                        {"text": "2. ⚡ Promos del Día", "callback_data": "menu:promociones#4"},
                    ],
                    [
                        {"text": "3. ⭐ Recomendados", "callback_data": "menu:mas_vendidos#4"},
                        {"text": "4. 🛒 Mi Carrito (Pagar)", "callback_data": "menu:carrito#4"},
                    ],
                    [
                        {"text": "5. 📋 Mis Pedidos", "callback_data": "menu:pedidos#4"},
                        {"text": "6. 🛵 Envíos y Horarios", "callback_data": "menu:horario#4"},
                    ],
                ]
            }


@pytest.mark.asyncio
async def test_telegram_hybrid_menu_ignored_if_out_of_range(mock_use_case):
    """Prueba que números fuera de rango no se conviertan en clics de menú y vayan al LLM."""
    store = FSMStateStore()
    user_id = "5391760292"
    fsm = TelegramConversationFSM(user_id, store)

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
            ),
        ):
            # Guardar opciones simuladas en FSM
            await fsm.set_state(
                FSMState.IN_MENU,
                {
                    "_menu_options": ["menu:categorias", "menu:promociones"],
                    "_allow_numeric_input": True,
                },
            )

            # Enviar opción "9" (fuera de rango)
            payload = {
                "message": {
                    "message_id": 10,
                    "from": {"id": int(user_id), "first_name": "TestUser"},
                    "chat": {"id": int(user_id), "type": "private"},
                    "date": 100000,
                    "text": "9",
                }
            }

            mock_use_case.execute.reset_mock()
            resp = await client.post("/telegram/webhook/fake_token", json=payload)
            assert resp.status_code == 200

            # Debe haber ejecutado el caso de uso de mensaje libre normal con el número 9
            mock_use_case.execute.assert_called_once()
            cmd = mock_use_case.execute.call_args[0][0]
            assert cmd.message == "9"
