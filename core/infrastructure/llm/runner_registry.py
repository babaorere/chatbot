"""
RunnerRegistry — Cache de ADK Runners por tenant.

Extrae la gestión del dict _runners / _runner_specs de LLMService
a una clase dedicada con responsabilidad única.

Un Runner se invalida y recrea cuando cambia el modelo o la instrucción
del tenant (detección por spec-tuple).
"""

from __future__ import annotations

import logging
import time

from google.adk import Agent, Runner
from google.adk.models.lite_llm import LiteLlm
from google.adk.sessions.base_session_service import BaseSessionService

from domain.tenant.schemas import TenantLLMConfig
from infrastructure.llm.key_resolver import APIKeyResolver

logger = logging.getLogger(__name__)

# Spec-tuple: (model_name, instruction) — si cambia, se invalida el runner
_RunnerSpec = tuple[str, str]


class RunnerRegistry:
    """Caché de ADK Runners por tenant.

    - Una instancia por proceso (singleton a nivel de app).
    - Crea/invalida runners cuando cambia la configuración del tenant.
    - Thread-safe para el caso de uso de un único event loop (asyncio).
    """

    def __init__(
        self,
        session_service: BaseSessionService,
        key_resolver: APIKeyResolver | None = None,
    ) -> None:
        """Inicializa el registro con el session service compartido.

        Args:
            session_service: Servicio de sesiones ADK (Redis o InMemory).
            key_resolver: Resolvedor de API keys. Si None, se crea uno por defecto.
        """
        self._session_service = session_service
        self._key_resolver = key_resolver or APIKeyResolver()
        self._runners: dict[str, Runner] = {}
        self._specs: dict[str, _RunnerSpec] = {}

    def get_runner(self, tenant_id: str, llm_config: TenantLLMConfig) -> Runner:
        """Retorna el Runner ADK para el tenant, creándolo o invalidándolo si cambia la spec.

        Args:
            tenant_id: Identificador único del tenant (str del UUID).
            llm_config: Configuración LLM actual del tenant.

        Returns:
            Runner: Instancia del ADK Runner lista para usar.

        Raises:
            RuntimeError: Si no se puede resolver la API key.
        """
        current_spec: _RunnerSpec = (llm_config.model_name, llm_config.instruction)

        if (
            tenant_id not in self._runners
            or self._specs.get(tenant_id) != current_spec
        ):
            self._runners[tenant_id] = self._build_runner(
                tenant_id=tenant_id,
                llm_config=llm_config,
            )
            self._specs[tenant_id] = current_spec

        return self._runners[tenant_id]

    def _build_runner(self, tenant_id: str, llm_config: TenantLLMConfig) -> Runner:
        """Construye un nuevo ADK Runner para el tenant dado usando config global.

        Args:
            tenant_id: Identificador del tenant.
            llm_config: Configuración LLM (solo se usa la instruction).

        Returns:
            Runner: Nueva instancia del ADK Runner configurada.
        """
        from config.settings import settings
        import os

        # Global model configuration with fallbacks
        api_key = settings.openrouter_api_key or os.getenv("OPENROUTER_API_KEY", "")

        # LiteLLM fallbacks configuration
        fallbacks = []
        if settings.fallback_model_1:
            fallbacks.append({"model": settings.fallback_model_1, "api_key": api_key})
        if settings.fallback_model_2:
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
            name=f"tenant_{tenant_id}_{int(time.time())}",
            model=model_obj,
            instruction=llm_config.instruction,
            tools=[],  # Las tools se configuran a nivel de tenant en fases futuras
        )

        runner = Runner(
            agent=agent,
            app_name=f"chatbot_{tenant_id}",
            session_service=self._session_service,
            auto_create_session=True,
        )

        logger.info(
            "Runner built for tenant=%s (global model=%s with fallbacks)",
            tenant_id,
            settings.model_name,
        )
        return runner

    def evict(self, tenant_id: str) -> None:
        """Invalida el runner de un tenant (útil cuando se actualiza su config).

        Args:
            tenant_id: Identificador del tenant a invalidar.
        """
        self._runners.pop(tenant_id, None)
        self._specs.pop(tenant_id, None)
        logger.debug("Runner evicted for tenant=%s", tenant_id)

    @property
    def active_tenants(self) -> list[str]:
        """Lista de tenant IDs con runners activos en caché."""
        return list(self._runners.keys())
