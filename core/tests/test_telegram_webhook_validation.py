import pytest
import httpx
from unittest.mock import patch, AsyncMock, MagicMock
from main import app
from app.container import get_process_message_uc
from infrastructure.channels.telegram_fsm import TelegramConversationFSM, FSMStateStore


@pytest.fixture(autouse=True)
def setup_mocks():
    """Override the use case dependency and clean up after each test to prevent pollution."""
    app.dependency_overrides[get_process_message_uc] = lambda: MagicMock()
    yield
    app.dependency_overrides.pop(get_process_message_uc, None)


@pytest.mark.asyncio
async def test_webhook_fails_when_redis_lock_cannot_be_acquired():
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        with (
            patch(
                "controllers.telegram_controller.get_redis_client"
            ) as redis_client_mock,
            patch(
                "controllers.telegram_controller.settings.telegram_bot_token",
                "fake_token",
            ),
        ):
            redis_instance = MagicMock()
            redis_instance.set = AsyncMock(side_effect=RuntimeError("redis down"))
            redis_client_mock.return_value = redis_instance

            payload = {
                "message": {
                    "message_id": 1,
                    "from": {"id": 111, "first_name": "Test"},
                    "chat": {"id": 111, "type": "private"},
                    "date": 100000,
                    "text": "hola",
                }
            }

            response = await client.post("/telegram/webhook/fake_token", json=payload)
            assert response.status_code == 500


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_json_payload():
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        with patch(
            "controllers.telegram_controller.settings.telegram_bot_token", "fake_token"
        ):
            response = await client.post(
                "/telegram/webhook/fake_token",
                content="{invalid-json",
                headers={"content-type": "application/json"},
            )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_webhook_rejects_payload_missing_user_or_chat_ids():
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        with patch(
            "controllers.telegram_controller.settings.telegram_bot_token", "fake_token"
        ):
            response = await client.post(
                "/telegram/webhook/fake_token",
                json={
                    "message": {
                        "message_id": 1,
                        "text": "hola",
                    }
                },
            )

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "detail": "invalid user_id or chat_id"}


@pytest.mark.asyncio
async def test_webhook_rejects_expired_callback_via_message_id():
    """Prueba que el webhook rechace un callback_query si el message_id no coincide con el menú activo (Capa 1)."""
    store = FSMStateStore()
    fsm = TelegramConversationFSM("user_capa1", store)
    await fsm.set_active_menu_id(9999)  # Menú activo actual es el ID 9999
    await fsm.increment_fsm_version()  # Establece la versión a 2

    # Parchear dependencias y configuración en services.telegram_service
    with (
        patch("controllers.telegram_controller.get_fsm_store", return_value=store),
        patch(
            "controllers.telegram_controller.settings.telegram_bot_token", "fake_token"
        ),
        patch("controllers.telegram_controller.JobDispatcher") as dispatcher_mock,
        patch(
            "controllers.telegram_controller.answer_telegram_callback_query",
            new_callable=AsyncMock,
        ) as mock_answer,
    ):
        dispatcher_instance = dispatcher_mock.return_value
        dispatcher_instance.enqueue_job = AsyncMock(return_value={"job_id": "job-1"})

        payload = {
            "callback_query": {
                "id": "query_123",
                "from": {"id": "user_capa1"},
                "message": {
                    "message_id": 8888,  # ID viejo/diferente
                    "chat": {"id": "user_capa1"},
                    "date": 1000000000,
                },
                "data": "menu:stock#2",
            }
        }

        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post("/telegram/webhook/fake_token", json=payload)
        assert response.status_code == 200

        # Debe haber respondido con alerta de expiración
        mock_answer.assert_called_once()
        assert mock_answer.call_args.kwargs["bot_token"] == "fake_token"
        assert mock_answer.call_args.kwargs["callback_query_id"] == "query_123"
        assert (
            mock_answer.call_args.kwargs["text"]
            == "Este menú ha expirado o ya no está activo."
        )
        assert mock_answer.call_args.kwargs["trace_id"].startswith("tg:user_capa1:")
        dispatcher_instance.enqueue_job.assert_awaited_once()
        assert (
            dispatcher_instance.enqueue_job.call_args.args[0]
            == "job_clear_reply_markup"
        )
        assert dispatcher_instance.enqueue_job.call_args.kwargs["message_id"] == 8888
        assert (
            dispatcher_instance.enqueue_job.call_args.kwargs["chat_id"] == "user_capa1"
        )


@pytest.mark.asyncio
async def test_webhook_rejects_expired_callback_via_version():
    """Prueba que el webhook rechace un callback si no hay active_menu_id pero la versión no coincide (Capa 2)."""
    store = FSMStateStore()
    fsm = TelegramConversationFSM("user_capa2", store)
    # No establecemos active_menu_id
    # Incrementar versión del FSM a 3
    await fsm.increment_fsm_version()
    await fsm.increment_fsm_version()

    with (
        patch("controllers.telegram_controller.get_fsm_store", return_value=store),
        patch(
            "controllers.telegram_controller.settings.telegram_bot_token", "fake_token"
        ),
        patch("controllers.telegram_controller.JobDispatcher") as dispatcher_mock,
        patch(
            "controllers.telegram_controller.answer_telegram_callback_query",
            new_callable=AsyncMock,
        ) as mock_answer,
    ):
        dispatcher_instance = dispatcher_mock.return_value
        dispatcher_instance.enqueue_job = AsyncMock(return_value={"job_id": "job-2"})

        payload = {
            "callback_query": {
                "id": "query_124",
                "from": {"id": "user_capa2"},
                "message": {
                    "message_id": 8888,
                    "chat": {"id": "user_capa2"},
                    "date": 1000000000,
                },
                "data": "menu:stock#2",  # Botón versión 2, pero FSM está en versión 3
            }
        }

        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post("/telegram/webhook/fake_token", json=payload)
        assert response.status_code == 200

        mock_answer.assert_called_once()
        assert mock_answer.call_args.kwargs["bot_token"] == "fake_token"
        assert mock_answer.call_args.kwargs["callback_query_id"] == "query_124"
        assert (
            mock_answer.call_args.kwargs["text"]
            == "Este menú ha expirado o ya no está activo."
        )
        assert mock_answer.call_args.kwargs["trace_id"].startswith("tg:user_capa2:")
        dispatcher_instance.enqueue_job.assert_awaited_once()
        assert (
            dispatcher_instance.enqueue_job.call_args.args[0]
            == "job_clear_reply_markup"
        )
        assert dispatcher_instance.enqueue_job.call_args.kwargs["message_id"] == 8888
        assert (
            dispatcher_instance.enqueue_job.call_args.kwargs["chat_id"] == "user_capa2"
        )
