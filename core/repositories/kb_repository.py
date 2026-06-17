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

    def find_by_tenant_id(
        self,
        tenant_id: uuid.UUID,
        category: str | None = None,
        active_only: bool = True,
        skip: int = 0,
        limit: int = 50,
    ) -> list[KnowledgeBase]:
        try:
            query = self.db.query(KnowledgeBase).filter(
                KnowledgeBase.tenant_id == tenant_id
            )
            if category:
                query = query.filter(KnowledgeBase.category == category)
            if active_only:
                query = query.filter(KnowledgeBase.is_active)
            return query.offset(skip).limit(limit).all()
        except Exception as e:
            logger.error(
                "KBRepository.find_by_tenant_id failed [tenant=%s]: %s", tenant_id, e
            )
            raise

    def find_by_id_and_tenant(
        self,
        entry_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> KnowledgeBase | None:
        try:
            return (
                self.db.query(KnowledgeBase)
                .filter(
                    KnowledgeBase.id == entry_id, KnowledgeBase.tenant_id == tenant_id
                )
                .first()
            )
        except Exception as e:
            logger.error(
                "KBRepository.find_by_id_and_tenant failed [id=%s, tenant=%s]: %s",
                entry_id,
                tenant_id,
                e,
            )
            raise

    def search_fts(
        self,
        tenant_id: uuid.UUID,
        query: str,
        top_k: int = 5,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        try:
            category_filter = "AND kb.category = :category" if category else ""
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
                WHERE kb.tenant_id = :tenant_id
                  AND kb.is_active = true
                  AND q.tsq @@ kb.search_vector
                  {category_filter}
                ORDER BY rank DESC
                LIMIT :top_k
            """.format(category_filter=category_filter)
            )

            params: dict[str, Any] = {
                "tenant_id": tenant_id,
                "query": query,
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
                    "rank": float(row["rank"]),
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(
                "KBRepository.search_fts failed [tenant=%s, query=%s]: %s",
                tenant_id,
                query,
                e,
            )
            raise

    def count_by_tenant(
        self,
        tenant_id: uuid.UUID,
        category: str | None = None,
        active_only: bool = True,
    ) -> int:
        try:
            query = self.db.query(KnowledgeBase).filter(
                KnowledgeBase.tenant_id == tenant_id
            )
            if category:
                query = query.filter(KnowledgeBase.category == category)
            if active_only:
                query = query.filter(KnowledgeBase.is_active)
            return query.count()
        except Exception as e:
            logger.error(
                "KBRepository.count_by_tenant failed [tenant=%s]: %s", tenant_id, e
            )
            raise

    def get_categories_by_tenant(
        self,
        tenant_id: uuid.UUID,
        active_only: bool = True,
    ) -> list[str]:
        try:
            query = self.db.query(KnowledgeBase.category).filter(
                KnowledgeBase.tenant_id == tenant_id
            )
            if active_only:
                query = query.filter(KnowledgeBase.is_active)
            return sorted(list(query.distinct().pluck("category")))
        except Exception as e:
            logger.error(
                "KBRepository.get_categories_by_tenant failed [tenant=%s]: %s",
                tenant_id,
                e,
            )
            raise

    def soft_delete_by_id_and_tenant(
        self,
        entry_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> bool:
        try:
            entry = self.find_by_id_and_tenant(entry_id, tenant_id)
            if not entry:
                return False
            entry.is_active = False
            self.db.flush()
            return True
        except Exception as e:
            logger.error(
                "KBRepository.soft_delete_by_id_and_tenant failed [id=%s, tenant=%s]: %s",
                entry_id,
                tenant_id,
                e,
            )
            raise
