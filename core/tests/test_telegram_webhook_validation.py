import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from main import app
from app.container import get_process_message_uc
from infrastructure.channels.telegram_fsm import TelegramConversationFSM, FSMStateStore

# Override the use case dependency to prevent dependency resolution errors (LLM provider not initialized, DB etc.)
app.dependency_overrides[get_process_message_uc] = lambda: MagicMock()

client = TestClient(app)


@pytest.mark.asyncio
async def test_webhook_rejects_expired_callback_via_message_id():
    """Prueba que el webhook rechace un callback_query si el message_id no coincide con el menú activo (Capa 1)."""
    store = FSMStateStore()
    fsm = TelegramConversationFSM("123456", store)
    await fsm.set_active_menu_id(9999)  # Menú activo actual es el ID 9999
    await fsm.increment_fsm_version()  # Establece la versión a 2

    # Parchear dependencias y configuración en services.telegram_service
    with patch("controllers.telegram_controller.get_fsm_store", return_value=store), \
         patch("controllers.telegram_controller.settings.telegram_bot_token", "fake_token"), \
         patch("services.telegram_service.answer_telegram_callback_query", new_callable=AsyncMock) as mock_answer, \
         patch("services.telegram_service.clear_telegram_reply_markup", new_callable=AsyncMock) as mock_clear:

        payload = {
            "callback_query": {
                "id": "query_123",
                "from": {"id": 123456},
                "message": {
                    "message_id": 8888,  # ID viejo/diferente
                    "chat": {"id": 123456},
                    "date": 1000000000
                },
                "data": "menu:stock#2"
            }
        }

        response = client.post("/telegram/webhook/fake_token", json=payload)
        assert response.status_code == 200

        # Debe haber respondido con alerta de expiración
        mock_answer.assert_called_once_with(
            bot_token="fake_token",
            callback_query_id="query_123",
            text="Este menú ha expirado o ya no está activo."
        )
        # Debe haber limpiado los botones del mensaje obsoleto
        mock_clear.assert_called_once_with(
            bot_token="fake_token",
            chat_id=123456,
            message_id=8888
        )


@pytest.mark.asyncio
async def test_webhook_rejects_expired_callback_via_version():
    """Prueba que el webhook rechace un callback si no hay active_menu_id pero la versión no coincide (Capa 2)."""
    store = FSMStateStore()
    fsm = TelegramConversationFSM("123456", store)
    # No establecemos active_menu_id
    # Incrementar versión del FSM a 3
    await fsm.increment_fsm_version()
    await fsm.increment_fsm_version()

    with patch("controllers.telegram_controller.get_fsm_store", return_value=store), \
         patch("controllers.telegram_controller.settings.telegram_bot_token", "fake_token"), \
         patch("services.telegram_service.answer_telegram_callback_query", new_callable=AsyncMock) as mock_answer, \
         patch("services.telegram_service.clear_telegram_reply_markup", new_callable=AsyncMock) as mock_clear:

        payload = {
            "callback_query": {
                "id": "query_124",
                "from": {"id": 123456},
                "message": {
                    "message_id": 8888,
                    "chat": {"id": 123456},
                    "date": 1000000000
                },
                "data": "menu:stock#2"  # Botón versión 2, pero FSM está en versión 3
            }
        }

        response = client.post("/telegram/webhook/fake_token", json=payload)
        assert response.status_code == 200

        mock_answer.assert_called_once_with(
            bot_token="fake_token",
            callback_query_id="query_124",
            text="Este menú ha expirado o ya no está activo."
        )
        mock_clear.assert_called_once_with(
            bot_token="fake_token",
            chat_id=123456,
            message_id=8888
        )
