"""
KBRAGProvider — Implementación de IRAGProvider usando KBRepository (full-text search).

Implementa el port IRAGProvider recuperando fragmentos relevantes de la
base de conocimiento y formateándolos como contexto para el LLM.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from repositories.kb_repository import KBRepository
from services.rag_policy import RAGPolicyService


logger = logging.getLogger(__name__)

_CONTEXT_TEMPLATE = "--- Fragmento {i} ({category}) ---\n{title}\n{content}\n"


class KBRAGProvider:
    """Recupera contexto relevante desde la base de conocimiento.

    Usa full-text search (FTS) de PostgreSQL a través de KBRepository.
    Compatible con el IRAGProvider Protocol.
    """

    def __init__(self, db: Session) -> None:
        """Inicializa el proveedor con la sesión de base de datos.

        Args:
            db: Sesión de base de datos (request-scoped).
        """
        self._db = db
        self._policy = RAGPolicyService()

    async def build_context(
        self,
        query: str,
        top_k: int = 5,
        category: str | None = None,
    ) -> str | None:
        """Recupera y formatea contexto relevante desde la KB.

        Realiza una búsqueda full-text con la query del usuario y devuelve
        los fragmentos más relevantes formateados para inyección en el prompt.
        Se excluyen consultas e información relacionada con productos,
        stock, precios, catálogo o intención de compra.

        Args:
            query: Texto de la consulta del usuario.
            top_k: Número máximo de fragmentos a recuperar.
            category: Filtro opcional por categoría de conocimiento.

        Returns:
            Contexto formateado o ``None`` si RAG debe omitirse.
        """
        policy_result = self._policy.classify(query)
        if not policy_result.allowed:
            logger.debug(
                "KBRAGProvider.build_context skipped per policy [intent=%s, reason='%s', query='%s']",
                policy_result.intent,
                policy_result.reason,
                query[:80],
            )
            return None

        if self._policy.is_blocked_category(category):
            logger.debug(
                "KBRAGProvider.build_context skipped blocked category='%s'", category
            )
            return None

        if not self._policy.is_safe_category(category):
            logger.debug(
                "KBRAGProvider.build_context skipped unsafe category='%s'", category
            )
            return None

        try:
            repo = KBRepository(self._db)
            results = repo.search_fts(
                query=query,
                top_k=top_k,
                category=category,
            )

            if not results:
                return None

            filtered_results = [
                result
                for result in results
                if not self._policy.is_blocked_category(result.get("category"))
            ]
            if not filtered_results:
                return None

            fragments = [
                _CONTEXT_TEMPLATE.format(
                    i=i + 1,
                    category=result.get("category", "general"),
                    title=result.get("title", ""),
                    content=result.get("content", ""),
                )
                for i, result in enumerate(filtered_results)
            ]

            return "\n".join(fragments)

        except Exception as e:
            logger.warning(
                "KBRAGProvider.build_context failed [query='%s']: %s — "
                "continuing without RAG context.",
                query[:50],
                e,
            )
            return None
