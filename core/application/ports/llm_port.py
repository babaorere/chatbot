"""
ILLMProvider — Port (Protocol) para proveedores de inferencia LLM.

Cualquier implementación concreta (ADK+LiteLlm, OpenAI directo, etc.)
debe satisfacer este contrato para ser intercambiable sin tocar
la lógica de aplicación.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, AsyncGenerator, Protocol, runtime_checkable

if TYPE_CHECKING:
    from domain.tenant.schemas import TenantLLMConfig


@runtime_checkable
class ILLMProvider(Protocol):
    """Contrato para proveedores de inferencia LLM multi-tenant."""

    async def run_chat(
        self,
        llm_config: "TenantLLMConfig",
        user_id: str,
        session_id: str,
        message: str,
        rag_context: str | None = None,
    ) -> str:
        """Ejecuta una inferencia síncrona y retorna la respuesta completa.

        Args:
            llm_config: Configuración LLM del tenant (modelo, api_key, instruction).
            user_id: Identificador externo del usuario (ej: Telegram user_id).
            session_id: Identificador de la sesión de conversación.
            message: Mensaje del usuario a procesar.
            rag_context: Contexto de conocimiento recuperado vía RAG, o None.

        Returns:
            str: Respuesta generada por el modelo.
        """
        ...

    async def run_chat_stream(
        self,
        llm_config: "TenantLLMConfig",
        user_id: str,
        session_id: str,
        message: str,
        rag_context: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Ejecuta una inferencia en modo streaming.

        Args:
            llm_config: Configuración LLM del tenant.
            user_id: Identificador externo del usuario.
            session_id: Identificador de la sesión de conversación.
            message: Mensaje del usuario a procesar.
            rag_context: Contexto de conocimiento recuperado vía RAG, o None.

        Yields:
            str: Fragmentos de texto (chunks) a medida que el modelo los genera.
        """
        ...

    async def get_session_history(
        self,
        llm_config: "TenantLLMConfig",
        user_id: str,
        session_id: str,
    ) -> list[dict[str, str]]:
        """Recupera el historial de mensajes de una sesión.

        Args:
            llm_config: Configuración LLM del tenant.
            user_id: Identificador externo del usuario.
            session_id: Identificador de la sesión de conversación.

        Returns:
            list[dict[str, str]]: Lista de mensajes con 'author' y 'content'.
        """
        ...
