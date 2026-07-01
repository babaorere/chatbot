import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from starlette.testclient import TestClient
from main import app
from app.container import get_process_message_uc
from infrastructure.channels.telegram_fsm import TelegramConversationFSM, FSMStateStore

client = TestClient(app)


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

    # 1. Parcheamos el envío a Telegram y la persistencia del FSM
    with (
        patch("controllers.telegram_controller.get_fsm_store", return_value=store),
        patch(
            "controllers.telegram_controller.settings.telegram_bot_token", "fake_token"
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
        resp = client.post("/telegram/webhook/fake_token", json=payload_start)
        assert resp.status_code == 200
        mock_use_case.clear_session.assert_not_awaited()
        mock_clear_latest_session.assert_awaited_once()
        mock_defer_clear_reply_markup.assert_not_called()

        # El FSM debe haber guardado las opciones del menú principal en el contexto
        ctx = await fsm.get_context()
        assert "_menu_options" in ctx
        assert ctx["_menu_options"] == [
            "menu:categorias",
            "menu:stock",
            "menu:precio",
            "menu:horario",
            "menu:contacto",
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
        mock_cat = MagicMock()
        mock_cat.name = "General"
        with patch(
            "services.category_service.CategoryService.list_categories",
            return_value=[mock_cat],
        ):
            resp2 = client.post("/telegram/webhook/fake_token", json=payload_option_1)
            assert resp2.status_code == 200

        # Debe haber enviado el listado de categorías a Telegram (con versión incrementada a 3)
        category_call = next(
            call
            for call in mock_send.call_args_list
            if call.kwargs.get("text")
            == "Selecciona una categoría para ver los productos disponibles:"
        )
        assert category_call.kwargs["bot_token"] == "fake_token"
        assert category_call.kwargs["chat_id"] == int(user_id)
        assert category_call.kwargs["reply_markup"] == {
            "inline_keyboard": [
                [{"text": "1. 🏷️ General", "callback_data": "cat_select:General#3"}],
                [
                    {
                        "text": "2. 🔙 Menú Principal",
                        "callback_data": "menu:back_to_main#3",
                    }
                ],
            ]
        }

        # 3. Enviar la opción "2" para volver al menú principal desde el menú de categorías
        payload_option_2 = {
            "message": {
                "message_id": 3,
                "from": {"id": int(user_id), "first_name": "TestUser"},
                "chat": {"id": int(user_id), "type": "private"},
                "date": 100010,
                "text": "2",
            }
        }
        resp3 = client.post("/telegram/webhook/fake_token", json=payload_option_2)
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
                    {
                        "text": "1. 🏷️ Ver Categorías",
                        "callback_data": "menu:categorias#4",
                    },
                    {
                        "text": "2. 📦 Consultar Stock",
                        "callback_data": "menu:stock#4",
                    },
                ],
                [
                    {"text": "3. 💰 Ver Precios", "callback_data": "menu:precio#4"},
                    {"text": "4. 🕒 Horarios", "callback_data": "menu:horario#4"},
                ],
                [
                    {
                        "text": "5. 👤 Hablar con Humano",
                        "callback_data": "menu:contacto#4",
                    }
                ],
            ]
        }


@pytest.mark.asyncio
async def test_telegram_hybrid_menu_ignored_if_out_of_range(mock_use_case):
    """Prueba que números fuera de rango no se conviertan en clics de menú y vayan al LLM."""
    store = FSMStateStore()
    user_id = "5391760292"
    fsm = TelegramConversationFSM(user_id, store)

    with (
        patch("controllers.telegram_controller.get_fsm_store", return_value=store),
        patch(
            "controllers.telegram_controller.settings.telegram_bot_token", "fake_token"
        ),
        patch(
            "controllers.telegram_controller.send_telegram_message",
            new_callable=AsyncMock,
        ),
    ):
        # Guardar opciones simuladas en FSM
        await fsm.set_state(
            await fsm.get_state(), {"_menu_options": ["menu:categorias", "menu:stock"]}
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
        resp = client.post("/telegram/webhook/fake_token", json=payload)
        assert resp.status_code == 200

        # Debe haber ejecutado el caso de uso de mensaje libre normal con el número 9
        mock_use_case.execute.assert_called_once()
        cmd = mock_use_case.execute.call_args[0][0]
        assert cmd.message == "9"
