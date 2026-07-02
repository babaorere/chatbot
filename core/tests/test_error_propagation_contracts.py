from __future__ import annotations

import builtins
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from agents.root_agent import contactar_humano, current_session_id_var
from app import container
from app.lifespan import lifespan
from controllers.telegram_controller import _get_human_agent_available
from config.settings import Settings
from application.use_cases.process_message import ProcessMessageUseCase


@pytest.mark.asyncio
async def test_contactar_humano_raises_when_pause_persistence_fails() -> None:
    token = current_session_id_var.set("session-123")
    db_mock = MagicMock()

    try:
        with patch("services.conversation_service.ConversationService") as svc_mock, patch(
            "config.database.SessionLocal", return_value=db_mock
        ):
            svc_instance = MagicMock()
            svc_instance.get_by_session_id.side_effect = RuntimeError("db down")
            svc_mock.return_value = svc_instance

            with pytest.raises(RuntimeError, match="Failed to pause conversation"):
                contactar_humano("motivo")
    finally:
        current_session_id_var.reset(token)


@pytest.mark.asyncio
async def test_process_message_clear_session_propagates_failure() -> None:
    db_mock = MagicMock()
    llm_mock = AsyncMock()
    llm_mock.clear_session.side_effect = RuntimeError("llm clear failed")
    use_case = ProcessMessageUseCase(
        db=db_mock,
        llm_provider=llm_mock,
        rag_provider=MagicMock(),
    )

    with pytest.raises(RuntimeError, match="llm clear failed"):
        await use_case.clear_session(user_id="u1", session_id="s1")


def test_settings_raises_on_unreadable_docker_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("os.path.exists", lambda path: path == "/run/secrets/jwt_secret")

    def _raising_open(*args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(builtins, "open", _raising_open)

    with pytest.raises(ValueError, match="No se pudo leer el secreto Docker 'jwt_secret'"):
        Settings.load_docker_secrets({})


@pytest.mark.asyncio
async def test_lifespan_aborts_when_migrations_fail() -> None:
    app = FastAPI()

    with patch("app.lifespan.Base.metadata.create_all"), patch(
        "app.lifespan._run_migrations", side_effect=RuntimeError("migration failed")
    ):
        with pytest.raises(RuntimeError, match="migration failed"):
            async with lifespan(app):
                pass


@pytest.mark.asyncio
async def test_clear_providers_raises_when_http_client_close_fails() -> None:
    http_client_mock = MagicMock()
    http_client_mock.aclose = AsyncMock(side_effect=RuntimeError("close failed"))

    container._http_client = http_client_mock

    try:
        with pytest.raises(RuntimeError, match="Failed to close global HTTP client"):
            await container.clear_providers()
    finally:
        container._http_client = None


def test_get_human_agent_available_raises_when_config_lookup_fails() -> None:
    db_mock = MagicMock()

    with patch("config.database.SessionLocal", return_value=db_mock), patch(
        "services.business_config_service.BusinessConfigService"
    ) as svc_mock:
        svc_instance = MagicMock()
        svc_instance.get_config.side_effect = RuntimeError("db down")
        svc_mock.return_value = svc_instance

        with pytest.raises(RuntimeError, match="Failed to resolve human agent availability"):
            _get_human_agent_available()
