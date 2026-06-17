"""
TenantLLMConfig — Schema Pydantic v2 para la configuración LLM de un tenant.

Reemplaza el dict JSON libre en `tenant.config` por un modelo tipado y validado.
Retro-compatible: puede construirse desde el dict existente via `TenantLLMConfig.from_tenant_config(...)`.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class LLMProviderEnum(str, Enum):
    """Proveedores LLM soportados."""

    OPENROUTER = "openrouter"
    GROQ = "groq"
    NVIDIA_NIM = "nvidia_nim"
    GEMINI = "gemini"
    UNKNOWN = "unknown"

    @classmethod
    def detect_from_model_name(cls, model_name: str) -> "LLMProviderEnum":
        """Detecta el proveedor a partir del nombre del modelo.

        Args:
            model_name: Nombre del modelo tal como se pasa a LiteLlm.

        Returns:
            LLMProviderEnum correspondiente al proveedor detectado.
        """
        model_lower = model_name.lower()
        if model_lower.startswith("openrouter/") or "openrouter" in model_lower:
            return cls.OPENROUTER
        if "groq" in model_lower:
            return cls.GROQ
        if "nvidia_nim" in model_lower or "nvidia" in model_lower:
            return cls.NVIDIA_NIM
        if "gemini" in model_lower or "google" in model_lower:
            return cls.GEMINI
        return cls.UNKNOWN


class TenantLLMConfig(BaseModel):
    """Configuración LLM validada por tenant.

    Sustituye el acceso libre a `tenant.config` dict.
    Garantiza que modelo, API key e instrucción siempre sean válidos
    antes de llegar al proveedor LLM.
    """

    model_config = ConfigDict(strict=False, populate_by_name=True)

    model_name: str = Field(
        default="openrouter/nvidia/nemotron-3-super-120b-a12b:free",
        description="Nombre del modelo en formato LiteLlm (ej: 'openrouter/...').",
    )
    api_key: SecretStr = Field(
        default=SecretStr(""),
        description="API key del proveedor. Si está vacía, se resuelve desde el entorno.",
    )
    instruction: str = Field(
        default="Eres un asistente virtual amable y profesional. Responde en español.",
        description="System prompt / instrucción del agente para este tenant.",
    )
    tools: list[str] = Field(
        default_factory=list,
        description="Nombres de tools registradas que el agente puede invocar.",
    )
    provider: LLMProviderEnum = Field(
        default=LLMProviderEnum.UNKNOWN,
        description="Proveedor detectado automáticamente desde model_name.",
    )

    @model_validator(mode="after")
    def _auto_detect_provider(self) -> "TenantLLMConfig":
        """Detecta el proveedor automáticamente si no fue especificado."""
        if self.provider == LLMProviderEnum.UNKNOWN:
            self.provider = LLMProviderEnum.detect_from_model_name(self.model_name)
        return self

    def resolve_api_key(self) -> str:
        """Resuelve la API key efectiva, fallando a variables de entorno si está vacía.

        Los tests de api_key que empiezan con 'sk-or-test-' o 'sk-test-'
        se tratan como vacías (placeholders de dev).

        Returns:
            str: API key efectiva lista para usar.

        Raises:
            RuntimeError: Si no se puede resolver ninguna API key válida.
        """
        raw = self.api_key.get_secret_value()
        is_placeholder = (
            not raw
            or raw.startswith("sk-or-test-")
            or raw.startswith("sk-test-")
        )
        if not is_placeholder:
            return raw

        # Fallback a variables de entorno según proveedor
        env_key = self._resolve_from_env()
        if not env_key:
            raise RuntimeError(
                f"No API key configured for model '{self.model_name}'. "
                f"Set the corresponding environment variable or configure api_key "
                f"for the tenant."
            )
        return env_key

    def _resolve_from_env(self) -> str | None:
        """Busca la API key en variables de entorno según el proveedor detectado."""
        mapping: dict[LLMProviderEnum, list[str]] = {
            LLMProviderEnum.OPENROUTER: ["OPENROUTER_API_KEY"],
            LLMProviderEnum.GROQ: ["GROQ_API_KEY"],
            LLMProviderEnum.NVIDIA_NIM: ["NVIDIA_API_KEY", "OPENROUTER_API_KEY"],
            LLMProviderEnum.GEMINI: ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
            LLMProviderEnum.UNKNOWN: ["OPENROUTER_API_KEY"],
        }
        for env_var in mapping.get(self.provider, ["OPENROUTER_API_KEY"]):
            value = os.getenv(env_var)
            if value:
                return value
        return None

    @classmethod
    def from_tenant_config(cls, config: dict[str, Any]) -> "TenantLLMConfig":
        """Construye un TenantLLMConfig desde el dict `tenant.config` legado.

        Retro-compatible con el esquema actual donde la config LLM
        vive en un JSON libre en la columna `config` del tenant.

        Args:
            config: Dict con claves 'model', 'api_key', 'instruction', 'tools'.

        Returns:
            TenantLLMConfig validado.
        """
        return cls(
            model_name=config.get("model", cls.model_fields["model_name"].default),
            api_key=SecretStr(config.get("api_key", "")),
            instruction=config.get("instruction", cls.model_fields["instruction"].default),
            tools=config.get("tools", []),
        )
