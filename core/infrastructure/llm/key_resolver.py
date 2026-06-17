"""
APIKeyResolver — Resuelve la API key efectiva para un TenantLLMConfig.

Extrae el if/elif de llm_service.py a una clase dedicada, testeable
de forma aislada y extensible a nuevos proveedores.
"""

from __future__ import annotations

import logging

from domain.tenant.schemas import TenantLLMConfig

logger = logging.getLogger(__name__)


class APIKeyResolver:
    """Resuelve la API key efectiva para un TenantLLMConfig.

    Delega la lógica de resolución al propio TenantLLMConfig
    (que ya conoce el proveedor y las env vars asociadas).
    Esta clase es el punto de extensión centralizado para
    estrategias de resolución más complejas (Vault, KMS, etc.).
    """

    def resolve(self, llm_config: TenantLLMConfig) -> str:
        """Retorna la API key efectiva para la configuración LLM dada.

        Intenta en orden:
        1. api_key configurada en el tenant (si no es placeholder de dev)
        2. Variable de entorno según el proveedor detectado

        Args:
            llm_config: Configuración LLM del tenant con modelo y api_key.

        Returns:
            str: API key válida lista para usar.

        Raises:
            RuntimeError: Si no se pudo resolver ninguna API key válida.
        """
        try:
            key = llm_config.resolve_api_key()
            logger.debug(
                "API key resolved for model '%s' (provider=%s)",
                llm_config.model_name,
                llm_config.provider.value,
            )
            return key
        except RuntimeError:
            logger.error(
                "Cannot resolve API key for model '%s' (provider=%s). "
                "Configure api_key on the tenant or set the corresponding env var.",
                llm_config.model_name,
                llm_config.provider.value,
            )
            raise
