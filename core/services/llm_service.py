from __future__ import annotations

import logging
import os
import time
from typing import Any, AsyncGenerator

from google.adk import Agent, Runner
from google.adk.models.lite_llm import LiteLlm
from google.adk.sessions.base_session_service import BaseSessionService
from google.genai import types

from models.tenant import Tenant
from services.session_service_factory import create_session_service

logger = logging.getLogger(__name__)


class LLMService:
    def __init__(self, session_service: BaseSessionService | None = None) -> None:
        self._runners: dict[str, Runner] = {}
        self._runner_specs: dict[str, tuple[str, str]] = {}
        self._session_service = session_service or create_session_service()

    def _get_runner(self, tenant: Tenant) -> Runner:
        tenant_key = str(tenant.id)
        current_spec = (tenant.get_instruction(),)

        if (
            tenant_key not in self._runners
            or self._runner_specs.get(tenant_key) != current_spec
        ):
            from config.settings import settings
            
            # Global model configuration with fallbacks
            api_key = settings.openrouter_api_key or os.getenv("OPENROUTER_API_KEY", "")
            
            # LiteLLM fallbacks configuration
            fallbacks = []
            if settings.fallback_model_1:
                fallbacks.append({"model": settings.fallback_model_1, "api_key": api_key})
            if settings.fallback_model_2:
                # determine api key for fallback 2
                fb2_key = api_key
                if "groq" in settings.fallback_model_2.lower():
                    fb2_key = settings.groq_api_key or os.getenv("GROQ_API_KEY", api_key)
                fallbacks.append({"model": settings.fallback_model_2, "api_key": fb2_key})

            model_obj = LiteLlm(
                model=settings.model_name, 
                api_key=api_key, 
                num_retries=3,
                fallbacks=fallbacks
            )

            agent = Agent(
                name=f"{tenant.slug}_{int(time.time())}",
                model=model_obj,
                instruction=tenant.get_instruction(),
                tools=[],
            )

            self._runners[tenant_key] = Runner(
                agent=agent,
                app_name=f"botilleria_{tenant_key}",
                session_service=self._session_service,
                auto_create_session=True,
            )
            self._runner_specs[tenant_key] = current_spec
            logger.info(
                "Runner created for tenant: %s (global model=%s with fallbacks)",
                tenant.slug,
                settings.model_name,
            )

        return self._runners[tenant_key]

    async def run_chat(
        self,
        tenant: Tenant,
        user_id: str,
        session_id: str,
        message: str,
        rag_context: str | None = None,
    ) -> str:
        try:
            runner = self._get_runner(tenant)
            full_response: list[str] = []
            content = types.Content(
                role="user",
                parts=[
                    types.Part(text=self._build_input_message(message, rag_context))
                ],
            )

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
                "LLMService.run_chat failed [tenant=%s, user=%s, session=%s]: %s",
                tenant.slug,
                user_id,
                session_id,
                e,
            )
            raise

    async def run_chat_stream(
        self,
        tenant: Tenant,
        user_id: str,
        session_id: str,
        message: str,
        rag_context: str | None = None,
    ) -> AsyncGenerator[str, None]:
        try:
            runner = self._get_runner(tenant)
            content = types.Content(
                role="user",
                parts=[
                    types.Part(text=self._build_input_message(message, rag_context))
                ],
            )

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
                "LLMService.run_chat_stream failed [tenant=%s, user=%s, session=%s]: %s",
                tenant.slug,
                user_id,
                session_id,
                e,
            )
            raise

    async def get_session_history(
        self,
        tenant: Tenant,
        user_id: str,
        session_id: str,
    ) -> list[dict[str, Any]]:
        try:
            runner = self._get_runner(tenant)
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
                "LLMService.get_session_history failed [tenant=%s, user=%s, session=%s]: %s",
                tenant.slug,
                user_id,
                session_id,
                e,
            )
            raise

    def _build_input_message(self, message: str, rag_context: str | None) -> str:
        if not rag_context:
            return message
        return (
            "CONTEXTO DE CONOCIMIENTO DEL NEGOCIO PARA ESTA CONSULTA:\n"
            f"{rag_context}\n\n"
            "Usa el contexto anterior solo si es relevante para responder. "
            "Si no alcanza, responde con honestidad y ofrece contactar a un humano.\n\n"
            f"MENSAJE DEL USUARIO:\n{message}"
        )


def create_llm_service(
    session_service: BaseSessionService | None = None,
) -> LLMService:
    return LLMService(session_service=session_service)
