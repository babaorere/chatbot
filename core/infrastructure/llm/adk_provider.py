"""
ADKLLMProvider — Implementación de ILLMProvider usando Google ADK + LiteLlm.

Implementa el port ILLMProvider delegando en:
- RunnerRegistry: gestiona el ciclo de vida de los ADK Runners por tenant
- APIKeyResolver: resuelve API keys de forma centralizada

ANTES: Toda esta lógica vivía en services/llm_service.py mezclando
       gestión de runners, resolución de keys e inferencia.
AHORA: Cada responsabilidad está en su clase correcta.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator

from google.adk.sessions.base_session_service import BaseSessionService
from google.genai import types

from domain.tenant.schemas import TenantLLMConfig
from infrastructure.llm.key_resolver import APIKeyResolver
from infrastructure.llm.runner_registry import RunnerRegistry

logger = logging.getLogger(__name__)


class ADKLLMProvider:
    """Implementa ILLMProvider usando Google ADK + LiteLlm + OpenRouter.

    Compatible con cualquier modelo soportado por LiteLlm:
    OpenRouter, Groq, NVIDIA NIM, Gemini, etc.

    Esta clase es un singleton por proceso (registrado en app/container.py).
    """

    def __init__(
        self,
        session_service: BaseSessionService,
        key_resolver: APIKeyResolver | None = None,
    ) -> None:
        """Inicializa el proveedor con el session service y runner registry.

        Args:
            session_service: Servicio de sesiones ADK compartido (Redis o InMemory).
            key_resolver: Resolvedor de API keys. Si None, se usa el default.
        """
        _resolver = key_resolver or APIKeyResolver()
        self._registry = RunnerRegistry(
            session_service=session_service,
            key_resolver=_resolver,
        )
        self._session_service = session_service

    async def run_chat(
        self,
        llm_config: TenantLLMConfig,
        user_id: str,
        session_id: str,
        message: str,
        rag_context: str | None = None,
    ) -> str:
        """Ejecuta una inferencia completa y retorna la respuesta como string.

        Args:
            llm_config: Configuración LLM del tenant.
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
            runner = self._registry.get_runner(
                tenant_id=llm_config.model_name,  # usado como clave de caché
                llm_config=llm_config,
            )
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
                "ADKLLMProvider.run_chat failed [model=%s, user=%s, session=%s]: %s",
                llm_config.model_name,
                user_id,
                session_id,
                e,
            )
            raise

    async def run_chat_stream(
        self,
        llm_config: TenantLLMConfig,
        user_id: str,
        session_id: str,
        message: str,
        rag_context: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Ejecuta una inferencia en modo streaming (SSE).

        Args:
            llm_config: Configuración LLM del tenant.
            user_id: Identificador del usuario.
            session_id: Identificador de la sesión de conversación.
            message: Mensaje del usuario.
            rag_context: Contexto RAG a inyectar en el prompt, o None.

        Yields:
            str: Fragmentos de texto a medida que el modelo los genera.
        """
        try:
            runner = self._registry.get_runner(
                tenant_id=llm_config.model_name,
                llm_config=llm_config,
            )
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
                "ADKLLMProvider.run_chat_stream failed "
                "[model=%s, user=%s, session=%s]: %s",
                llm_config.model_name,
                user_id,
                session_id,
                e,
            )
            raise

    async def get_session_history(
        self,
        llm_config: TenantLLMConfig,
        user_id: str,
        session_id: str,
    ) -> list[dict[str, Any]]:
        """Recupera el historial de mensajes de una sesión ADK.

        Args:
            llm_config: Configuración LLM del tenant.
            user_id: Identificador del usuario.
            session_id: Identificador de la sesión.

        Returns:
            list[dict[str, str]]: Lista de mensajes con 'author' y 'content'.
        """
        try:
            runner = self._registry.get_runner(
                tenant_id=llm_config.model_name,
                llm_config=llm_config,
            )
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
                "ADKLLMProvider.get_session_history failed "
                "[model=%s, user=%s, session=%s]: %s",
                llm_config.model_name,
                user_id,
                session_id,
                e,
            )
            raise

    def evict_runner(self, tenant_id: str) -> None:
        """Invalida el runner de un tenant para forzar recreación.

        Útil cuando el admin actualiza la configuración LLM del tenant.

        Args:
            tenant_id: Identificador del tenant cuyo runner debe invalidarse.
        """
        self._registry.evict(tenant_id)

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

        return types.Content(
            role="user",
            parts=[types.Part(text=text)],
        )
