from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from models.knowledge_base import KnowledgeBase
from repositories.base import JpaRepository

logger = logging.getLogger(__name__)


class KBRepository(JpaRepository[KnowledgeBase]):
    def __init__(self, db: Session) -> None:
        super().__init__(KnowledgeBase, db)

    def find_all(
        self,
        category: str | None = None,
        active_only: bool = True,
        skip: int = 0,
        limit: int = 50,
    ) -> list[KnowledgeBase]:
        try:
            query = self.db.query(KnowledgeBase)
            if category:
                query = query.filter(KnowledgeBase.category == category)
            if active_only:
                query = query.filter(KnowledgeBase.is_active)
            return query.offset(skip).limit(limit).all()
        except Exception as e:
            logger.error("KBRepository.find_all failed: %s", e)
            raise

    def find_by_id(
        self,
        entry_id: uuid.UUID,
    ) -> KnowledgeBase | None:
        try:
            return (
                self.db.query(KnowledgeBase)
                .filter(KnowledgeBase.id == entry_id)
                .first()
            )
        except Exception as e:
            logger.error(
                "KBRepository.find_by_id failed [id=%s]: %s",
                entry_id,
                e,
            )
            raise

    def search_hybrid(
        self,
        query: str,
        query_vector: list[float] | None = None,
        top_k: int = 5,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        try:
            category_filter = "AND kb.category = :category" if category else ""

            # Si no hay vector, usamos FTS puro
            if not query_vector:
                sql = text(
                    """
                    WITH q AS (
                        SELECT replace(
                            plainto_tsquery('spanish', immutable_unaccent(:query))::text,
                            ' & ', ' | '
                        )::tsquery AS tsq
                    )
                    SELECT
                        kb.id,
                        kb.category,
                        kb.title,
                        kb.content,
                        ts_rank(kb.search_vector, q.tsq) AS rank
                    FROM knowledge_base kb, q
                    WHERE kb.is_active = true
                      AND q.tsq @@ kb.search_vector
                      {category_filter}
                    ORDER BY rank DESC
                    LIMIT :top_k
                """.format(category_filter=category_filter)
                )
                params: dict[str, Any] = {"query": query, "top_k": top_k}
                if category:
                    params["category"] = category
                result = self.db.execute(sql, params)
                rows = result.mappings().all()
                return [
                    {
                        "id": str(row["id"]),
                        "category": row["category"],
                        "title": row["title"],
                        "content": row["content"],
                        "rank": float(row["rank"]),
                    }
                    for row in rows
                ]

            # Si hay vector, realizamos búsqueda híbrida combinando FTS y pgvector (Similitud del Coseno)
            sql = text(
                """
                WITH q AS (
                    SELECT replace(
                        plainto_tsquery('spanish', immutable_unaccent(:query))::text,
                        ' & ', ' | '
                    )::tsquery AS tsq
                )
                SELECT
                    kb.id,
                    kb.category,
                    kb.title,
                    kb.content,
                    (1.0 - (kb.embedding <=> CAST(:query_vector AS vector))) AS vector_similarity,
                    coalesce(ts_rank(kb.search_vector, q.tsq), 0.0) AS fts_rank
                FROM knowledge_base kb, q
                WHERE kb.is_active = true
                  AND (q.tsq @@ kb.search_vector OR kb.embedding IS NOT NULL)
                  {category_filter}
                ORDER BY (0.7 * (1.0 - (kb.embedding <=> CAST(:query_vector AS vector)))) + (0.3 * coalesce(ts_rank(kb.search_vector, q.tsq), 0.0)) DESC
                LIMIT :top_k
            """.format(category_filter=category_filter)
            )

            params = {
                "query": query,
                "query_vector": query_vector,
                "top_k": top_k,
            }
            if category:
                params["category"] = category

            result = self.db.execute(sql, params)
            rows = result.mappings().all()
            return [
                {
                    "id": str(row["id"]),
                    "category": row["category"],
                    "title": row["title"],
                    "content": row["content"],
                    "rank": float(
                        (0.7 * float(row["vector_similarity"]))
                        + (0.3 * float(row["fts_rank"]))
                    ),
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(
                "KBRepository.search_hybrid failed [query=%s]: %s",
                query,
                e,
            )
            raise

    def search_fts(
        self,
        query: str,
        top_k: int = 5,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.search_hybrid(
            query=query, query_vector=None, top_k=top_k, category=category
        )

    def count_all(
        self,
        category: str | None = None,
        active_only: bool = True,
    ) -> int:
        try:
            query = self.db.query(KnowledgeBase)
            if category:
                query = query.filter(KnowledgeBase.category == category)
            if active_only:
                query = query.filter(KnowledgeBase.is_active)
            return query.count()
        except Exception as e:
            logger.error("KBRepository.count_all failed: %s", e)
            raise

    def get_categories(
        self,
        active_only: bool = True,
    ) -> list[str]:
        try:
            query = self.db.query(KnowledgeBase.category)
            if active_only:
                query = query.filter(KnowledgeBase.is_active)
            return sorted(list(query.distinct().pluck("category")))
        except Exception as e:
            logger.error("KBRepository.get_categories failed: %s", e)
            raise

    def soft_delete(
        self,
        entry_id: uuid.UUID,
    ) -> bool:
        try:
            entry = self.find_by_id(entry_id)
            if not entry:
                return False
            entry.is_active = False
            self.db.flush()
            return True
        except Exception as e:
            logger.error(
                "KBRepository.soft_delete failed [id=%s]: %s",
                entry_id,
                e,
            )
            raise
