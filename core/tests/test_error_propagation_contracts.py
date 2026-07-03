from __future__ import annotations

import builtins
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from agents.root_agent import contactar_humano, current_session_id_var
from app import container
from app.lifespan import lifespan
from application.use_cases.commands import ProcessMessageCommand
from controllers.telegram_controller import _get_human_agent_available
from controllers.telegram_controller import prime_human_agent_cache
from config.settings import Settings
from application.use_cases.process_message import ProcessMessageUseCase
from services.session_service_factory import create_session_service


@pytest.mark.asyncio
async def test_contactar_humano_raises_when_pause_persistence_fails() -> None:
    token = current_session_id_var.set("session-123")
    db_mock = MagicMock()

    try:
        with (
            patch("agents.root_agent.SessionLocal", return_value=db_mock),
            patch("agents.root_agent.ConversationService") as svc_mock,
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


@pytest.mark.asyncio
async def test_process_message_raises_when_user_lookup_fails() -> None:
    db_mock = MagicMock()
    llm_mock = AsyncMock()
    rag_mock = AsyncMock()
    dispatcher_mock = AsyncMock()
    use_case = ProcessMessageUseCase(
        db=db_mock,
        llm_provider=llm_mock,
        rag_provider=rag_mock,
        job_dispatcher=dispatcher_mock,
    )

    with patch.object(
        ProcessMessageUseCase,
        "_get_or_create_user",
        side_effect=RuntimeError("user lookup down"),
    ):
        with pytest.raises(RuntimeError, match="user lookup down"):
            await use_case.execute(
                ProcessMessageCommand(
                    user_id="u1",
                    platform="telegram",
                    message="hola",
                )
            )

    llm_mock.run_chat.assert_not_awaited()
    dispatcher_mock.enqueue_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_message_raises_when_conversation_creation_fails() -> None:
    db_mock = MagicMock()
    llm_mock = AsyncMock()
    rag_mock = AsyncMock()
    dispatcher_mock = AsyncMock()
    user_mock = MagicMock(id=1)
    use_case = ProcessMessageUseCase(
        db=db_mock,
        llm_provider=llm_mock,
        rag_provider=rag_mock,
        job_dispatcher=dispatcher_mock,
    )

    with (
        patch.object(
            ProcessMessageUseCase,
            "_get_or_create_user",
            return_value=user_mock,
        ),
        patch.object(
            ProcessMessageUseCase,
            "_ensure_conversation",
            side_effect=RuntimeError("conversation broken"),
        ),
    ):
        with pytest.raises(RuntimeError, match="conversation broken"):
            await use_case.execute(
                ProcessMessageCommand(
                    user_id="u1",
                    platform="telegram",
                    message="hola",
                )
            )

    llm_mock.run_chat.assert_not_awaited()
    dispatcher_mock.enqueue_job.assert_not_awaited()


def test_settings_raises_on_unreadable_docker_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "os.path.exists", lambda path: path == "/run/secrets/jwt_secret"
    )

    def _raising_open(*args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(builtins, "open", _raising_open)

    with pytest.raises(
        ValueError, match="No se pudo leer el secreto Docker 'jwt_secret'"
    ):
        Settings.load_docker_secrets({})


@pytest.mark.asyncio
async def test_lifespan_aborts_when_migrations_fail() -> None:
    app = FastAPI()

    with (
        patch("app.lifespan.Base.metadata.create_all"),
        patch(
            "app.lifespan._run_migrations", side_effect=RuntimeError("migration failed")
        ),
    ):
        with pytest.raises(RuntimeError, match="migration failed"):
            async with lifespan(app):
                pass


@pytest.mark.asyncio
async def test_lifespan_seeds_general_catalog_only_in_development() -> None:
    app = FastAPI()
    seed_session_cm = MagicMock()
    seed_db = MagicMock()
    seed_session_cm.__enter__.return_value = seed_db
    seed_session_cm.__exit__.return_value = None

    config_mock = MagicMock(human_agent_available=True)

    with (
        patch("app.lifespan.Base.metadata.create_all"),
        patch("app.lifespan._run_migrations"),
        patch("app.lifespan.SessionLocal", return_value=seed_session_cm),
        patch("app.lifespan.BusinessConfigRepository") as repo_mock,
        patch("app.lifespan.create_session_service", return_value=MagicMock()),
        patch("app.lifespan.ADKLLMProvider", return_value=MagicMock()),
        patch("app.lifespan.set_llm_provider"),
        patch("app.container.get_http_client", return_value=MagicMock()),
        patch("app.lifespan.seed_general") as seed_general_mock,
    ):
        repo_mock.return_value.get_config.return_value = config_mock
        seed_db.commit.return_value = None
        with (
            patch("app.lifespan.settings.app_env", "development"),
            patch("app.lifespan.settings.session_backend", "memory"),
        ):
            async with lifespan(app):
                pass

    seed_general_mock.assert_called_once_with(reset_existing_products=True)


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

    with (
        patch(
            "controllers.telegram_controller._human_agent_cache",
            {"value": True, "expires_at": 0},
        ),
        patch("controllers.telegram_controller.SessionLocal", return_value=db_mock),
        patch("controllers.telegram_controller.BusinessConfigService") as svc_mock,
    ):
        svc_instance = MagicMock()
        svc_instance.get_config.side_effect = RuntimeError("db down")
        svc_mock.return_value = svc_instance

        with pytest.raises(
            RuntimeError, match="Failed to resolve human agent availability"
        ):
            _get_human_agent_available()


def test_get_human_agent_available_uses_primed_cache_without_db_lookup() -> None:
    prime_human_agent_cache(False, ttl_seconds=300)

    with patch("controllers.telegram_controller.SessionLocal") as session_local_mock:
        assert _get_human_agent_available() is False

    session_local_mock.assert_not_called()


def test_create_session_service_raises_when_redis_factory_fails() -> None:
    with patch(
        "services.session_service_factory.create_redis_client",
        side_effect=RuntimeError("redis down"),
    ):
        with pytest.raises(RuntimeError, match="redis down"):
            create_session_service(
                config=Settings(
                    session_backend="redis",
                    redis_url="redis://localhost:6379/0",
                )
            )
