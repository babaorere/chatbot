"""
ProcessMessageCommand / ProcessMessageResult — DTOs del use case principal.

Objetos de transferencia inmutables que cruzan la frontera entre
la capa de interfaz y la capa de aplicación.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProcessMessageCommand:
    """Comando de entrada para procesar un mensaje de usuario."""

    user_id: str
    """Identificador externo del usuario en la plataforma."""

    platform: str
    """Canal de origen: 'telegram', 'rest', 'whatsapp', etc."""

    message: str
    """Texto del mensaje a procesar."""

    session_id: str | None = None
    """ID de sesión existente. Si es None, se crea una nueva."""

    metadata: dict[str, str] = field(default_factory=dict)
    """Metadatos adicionales del canal (ej: chat_id de Telegram)."""


@dataclass(frozen=True)
class ProcessMessageResult:
    """Resultado de procesar un mensaje de usuario."""

    response: str
    """Texto de respuesta generado por el LLM."""

    session_id: str
    """ID de la sesión usada (nueva o existente)."""

    user_id: str
    """Identificador externo del usuario."""
