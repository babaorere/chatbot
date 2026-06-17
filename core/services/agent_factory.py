"""
Factoría dinámica de agentes ADK por usuario.
Cada usuario recibe una instancia aislada con su propio contexto
de conversación y configuración de memoria.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentContext:
    user_id: int
    session_id: str
    platform: str
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentFactory:
    """
    Crea y cachea instancias de agente ADK por (user_id, session_id).
    La implementación concreta se vinculará cuando integremos google/adk-python.
    """

    _registry: dict[str, Any] = {}

    @classmethod
    def _key(cls, ctx: AgentContext) -> str:
        return f"{ctx.user_id}:{ctx.session_id}"

    @classmethod
    def get_or_create(cls, ctx: AgentContext) -> Any:
        key = cls._key(ctx)
        if key not in cls._registry:
            cls._registry[key] = cls._build_agent(ctx)
        return cls._registry[key]

    @classmethod
    def _build_agent(cls, ctx: AgentContext) -> dict[str, Any]:
        """
        Placeholder: aquí se instanciará el agente ADK real con su
        configuración de memoria, tools y system prompt por usuario.
        """
        return {
            "user_id": ctx.user_id,
            "session_id": ctx.session_id,
            "platform": ctx.platform,
            "status": "initialized",
        }

    @classmethod
    def evict(cls, ctx: AgentContext) -> None:
        cls._registry.pop(cls._key(ctx), None)
