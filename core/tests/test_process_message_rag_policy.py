from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from application.use_cases.commands import ProcessMessageCommand, ProcessMessageResult
from application.use_cases.process_message import ProcessMessageUseCase


class RecordingLLMProvider:
    def __init__(self) -> None:
        self.rag_context: str | None = None

    async def run_chat(
        self,
        user_id: str,
        session_id: str,
        message: str,
        rag_context: str | None,
    ) -> str:
        self.rag_context = rag_context
        return "respuesta"


class RecordingRAGProvider:
    async def build_context(
        self,
        query: str,
        top_k: int = 5,
        category: str | None = None,
    ) -> str:
        return f"contexto:{query}"


class BlockingRAGProvider:
    async def build_context(
        self,
        query: str,
        top_k: int = 5,
        category: str | None = None,
    ) -> str:
        raise AssertionError("RAG should not be called")


@pytest.fixture
def patched_services() -> tuple[MagicMock, MagicMock]:
    user = MagicMock(id=1)

    with (
        patch("services.user_service.UserService") as user_service_cls,
        patch("services.conversation_service.ConversationService") as conv_service_cls,
    ):
        user_service_cls.return_value.get_or_create.return_value = user
        conv_service_cls.return_value.get_by_session_id.return_value = MagicMock()
        yield user_service_cls, conv_service_cls


@pytest.mark.asyncio
async def test_process_message_skips_rag_for_product_query(
    patched_services: tuple[MagicMock, MagicMock],
) -> None:
    llm = RecordingLLMProvider()
    use_case = ProcessMessageUseCase(MagicMock(), llm, BlockingRAGProvider())

    result = await use_case.execute(
        ProcessMessageCommand(
            user_id="user-1",
            platform="telegram",
            message="¿Tienen pisco sour?",
        )
    )

    assert result == ProcessMessageResult(
        response="respuesta",
        session_id=result.session_id,
        user_id="user-1",
    )
    assert llm.rag_context is None


@pytest.mark.asyncio
async def test_process_message_builds_rag_for_general_service_query(
    patched_services: tuple[MagicMock, MagicMock],
) -> None:
    llm = RecordingLLMProvider()
    rag = RecordingRAGProvider()
    use_case = ProcessMessageUseCase(MagicMock(), llm, rag)

    result = await use_case.execute(
        ProcessMessageCommand(
            user_id="user-1",
            platform="telegram",
            message="¿Cuál es el horario de atención?",
        )
    )

    assert result.response == "respuesta"
    assert llm.rag_context == "contexto:¿Cuál es el horario de atención?"
