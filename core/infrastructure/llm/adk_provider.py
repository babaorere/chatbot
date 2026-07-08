"""
ADKLLMProvider — Implementación de ILLMProvider usando Google ADK + LiteLlm.

Delegará la ejecución al agente central definido en `agents.root_agent`.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator

from google.genai import types
from agents.constants import GADK_APP_NAME

logger = logging.getLogger(__name__)


def _get_runner() -> Any:
    from agents.root_agent import get_runner

    return get_runner()


class ADKLLMProvider:
    """Implementa ILLMProvider usando Google ADK + LiteLlm + OpenRouter.

    Esta clase es un singleton por proceso (registrado en app/container.py).
    """

    def __init__(
        self,
        session_service: Any,
    ) -> None:
        """Inicializa el proveedor con el session service.

        Args:
            session_service: Servicio de sesiones ADK compartido.
        """
        self._session_service = session_service

    async def run_chat(
        self,
        user_id: str,
        session_id: str,
        message: str,
        rag_context: str | None = None,
    ) -> str:
        """Ejecuta una inferencia completa y retorna la respuesta como string.

        Args:
            user_id: Identificador del usuario.
            session_id: Identificador de la sesión de conversación.
            message: Mensaje del usuario.
            rag_context: Contexto RAG a inyectar en el prompt, o None.

        Returns:
            str: Respuesta generada por el modelo.

        Raises:
            RuntimeError: Si el modelo no puede generar respuesta.
        """
        try:
            runner = _get_runner()
            content = self._build_content(message, rag_context)
            full_response: list[str] = []

            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=content,
            ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text and not getattr(part, "thought", False):
                            full_response.append(part.text)

            return (
                "".join(full_response)
                if full_response
                else "No pude generar una respuesta."
            )

        except Exception as e:
            logger.error(
                "ADKLLMProvider.run_chat failed [user=%s, session=%s]: %s",
                user_id,
                session_id,
                e,
            )
            raise

    async def run_chat_stream(
        self,
        user_id: str,
        session_id: str,
        message: str,
        rag_context: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Ejecuta una inferencia en modo streaming (SSE).

        Args:
            user_id: Identificador del usuario.
            session_id: Identificador de la sesión de conversación.
            message: Mensaje del usuario.
            rag_context: Contexto RAG a inyectar en el prompt, o None.

        Yields:
            str: Fragmentos de texto a medida que el modelo los genera.
        """
        try:
            runner = _get_runner()
            content = self._build_content(message, rag_context)

            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=content,
            ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text and not getattr(part, "thought", False):
                            yield part.text

        except Exception as e:
            logger.error(
                "ADKLLMProvider.run_chat_stream failed [user=%s, session=%s]: %s",
                user_id,
                session_id,
                e,
            )
            raise

    async def get_session_history(
        self,
        user_id: str,
        session_id: str,
    ) -> list[dict[str, Any]]:
        """Recupera el historial de mensajes de una sesión ADK.

        Args:
            user_id: Identificador del usuario.
            session_id: Identificador de la sesión.

        Returns:
            list[dict[str, str]]: Lista de mensajes con 'author' y 'content'.
        """
        try:
            runner = _get_runner()
            session = await self._session_service.get_session(
                app_name=runner.app_name,
                user_id=user_id,
                session_id=session_id,
            )
            if not session:
                return []

            history: list[dict[str, Any]] = []
            for event in session.events:
                if event.content and event.content.parts:
                    texts = [p.text for p in event.content.parts if p.text]
                    if texts:
                        history.append(
                            {"author": event.author, "content": "".join(texts)}
                        )
            return history

        except Exception as e:
            logger.error(
                "ADKLLMProvider.get_session_history failed [user=%s, session=%s]: %s",
                user_id,
                session_id,
                e,
            )
            raise

    async def clear_session(
        self,
        user_id: str,
        session_id: str,
    ) -> None:
        """Elimina el historial y limpia la sesión conversacional de ADK."""
        try:
            await self._session_service.delete_session(
                app_name=GADK_APP_NAME,
                user_id=user_id,
                session_id=session_id,
            )
            logger.info("Cleared ADK session %s for user %s", session_id, user_id)
        except Exception as e:
            logger.error(
                "ADKLLMProvider.clear_session failed [user=%s, session=%s]: %s",
                user_id,
                session_id,
                e,
            )
            raise

    @staticmethod
    def _build_content(message: str, rag_context: str | None) -> types.Content:
        """Construye el objeto Content de ADK con el mensaje y contexto RAG.

        Args:
            message: Mensaje del usuario.
            rag_context: Contexto RAG opcional a inyectar.

        Returns:
            types.Content: Objeto Content listo para pasar al runner.
        """
        if rag_context:
            text = (
                "CONTEXTO DE CONOCIMIENTO DEL NEGOCIO PARA ESTA CONSULTA:\n"
                f"{rag_context}\n\n"
                "Usa el contexto anterior solo si es relevante para responder. "
                "Si no alcanza, responde con honestidad y ofrece contactar a un humano.\n\n"
                f"MENSAJE DEL USUARIO:\n{message}"
            )
        else:
            text = message

        text = f"{text}\n\nREGLA FINAL DE IDIOMA: responde exclusivamente en español."

        return types.Content(
            role="user",
            parts=[types.Part(text=text)],
        )
