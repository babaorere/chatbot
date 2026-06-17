"""
KBRAGProvider — Implementación de IRAGProvider usando KBRepository (full-text search).

Implementa el port IRAGProvider recuperando fragmentos relevantes de la
base de conocimiento del tenant y formateándolos como contexto para el LLM.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)

_CONTEXT_TEMPLATE = (
    "--- Fragmento {i} ({category}) ---\n"
    "{title}\n"
    "{content}\n"
)


class KBRAGProvider:
    """Recupera contexto relevante desde la base de conocimiento del tenant.

    Usa full-text search (FTS) de PostgreSQL a través de KBRepository.
    Compatible con el IRAGProvider Protocol.
    """

    def __init__(self, db: Session) -> None:
        """Inicializa el proveedor con la sesión de base de datos.

        Args:
            db: Sesión de base de datos (request-scoped).
        """
        self._db = db

    async def build_context(
        self,
        query: str,
        tenant_id: uuid.UUID,
        top_k: int = 5,
        category: str | None = None,
    ) -> str | None:
        """Recupera y formatea contexto relevante desde la KB del tenant.

        Realiza una búsqueda full-text con la query del usuario y devuelve
        los fragmentos más relevantes formateados para inyección en el prompt.

        Args:
            query: Texto del mensaje del usuario a usar como consulta.
            tenant_id: UUID del tenant cuya KB se consulta.
            top_k: Número máximo de fragmentos a recuperar.
            category: Filtro opcional por categoría de conocimiento.

        Returns:
            str | None: Fragmentos formateados listos para el LLM,
                o None si no se encontraron resultados relevantes.
        """
        try:
            from repositories.kb_repository import KBRepository  # noqa: PLC0415

            repo = KBRepository(self._db)
            results = repo.search_fts(
                tenant_id=tenant_id,
                query=query,
                top_k=top_k,
                category=category,
            )

            if not results:
                return None

            fragments = [
                _CONTEXT_TEMPLATE.format(
                    i=i + 1,
                    category=r.get("category", "general"),
                    title=r.get("title", ""),
                    content=r.get("content", ""),
                )
                for i, r in enumerate(results)
            ]

            return "\n".join(fragments)

        except Exception as e:
            logger.warning(
                "KBRAGProvider.build_context failed [tenant=%s, query='%s']: %s — "
                "continuing without RAG context.",
                tenant_id,
                query[:50],
                e,
            )
            # RAG es best-effort: si falla, continuamos sin contexto
            return None
