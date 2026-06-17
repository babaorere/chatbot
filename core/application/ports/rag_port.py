"""
IRAGProvider — Port (Protocol) para proveedores de recuperación de contexto RAG.

Desacopla la lógica de recuperación (full-text search, embeddings, etc.)
del use case de procesamiento de mensajes.
"""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable


@runtime_checkable
class IRAGProvider(Protocol):
    """Contrato para proveedores de contexto RAG por tenant."""

    async def build_context(
        self,
        query: str,
        tenant_id: uuid.UUID,
        top_k: int = 5,
        category: str | None = None,
    ) -> str | None:
        """Recupera y formatea contexto relevante para la consulta del usuario.

        Invoca este método antes de llamar al LLM para enriquecer el prompt
        con información de la base de conocimiento del tenant.

        Args:
            query: Texto del mensaje del usuario a usar como consulta de búsqueda.
            tenant_id: UUID del tenant cuya base de conocimiento se consulta.
            top_k: Número máximo de fragmentos a recuperar.
            category: Filtro opcional por categoría de conocimiento.

        Returns:
            str | None: Contexto formateado listo para inyectar en el prompt,
                o None si no se encontraron fragmentos relevantes.
        """
        ...
