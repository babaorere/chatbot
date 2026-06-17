from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from models.knowledge_base import KnowledgeBase
from repositories.kb_repository import KBRepository

logger = logging.getLogger(__name__)


class KBService:
    def __init__(self, db: Session, tenant_id: uuid.UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.repo = KBRepository(db)

    def list_entries(
        self,
        category: str | None = None,
        active_only: bool = True,
        skip: int = 0,
        limit: int = 50,
    ) -> list[KnowledgeBase]:
        try:
            return self.repo.find_by_tenant_id(
                self.tenant_id,
                category=category,
                active_only=active_only,
                skip=skip,
                limit=limit,
            )
        except Exception as e:
            logger.error(
                "KBService.list_entries failed [tenant=%s]: %s", self.tenant_id, e
            )
            raise

    def get_entry(self, entry_id: uuid.UUID) -> KnowledgeBase | None:
        try:
            return self.repo.find_by_id_and_tenant(entry_id, self.tenant_id)
        except Exception as e:
            logger.error(
                "KBService.get_entry failed [id=%s, tenant=%s]: %s",
                entry_id,
                self.tenant_id,
                e,
            )
            raise

    def create_entry(
        self,
        category: str,
        title: str,
        content: str,
    ) -> KnowledgeBase:
        try:
            entry = KnowledgeBase(
                tenant_id=self.tenant_id,
                category=category,
                title=title,
                content=content,
            )
            return self.repo.save(entry)
        except Exception as e:
            logger.error(
                "KBService.create_entry failed [tenant=%s, category=%s]: %s",
                self.tenant_id,
                category,
                e,
            )
            raise

    def update_entry(
        self,
        entry_id: uuid.UUID,
        category: str | None = None,
        title: str | None = None,
        content: str | None = None,
        is_active: bool | None = None,
    ) -> KnowledgeBase:
        try:
            entry = self.repo.find_by_id_and_tenant(entry_id, self.tenant_id)
            if not entry:
                raise ValueError(
                    f"Knowledge base entry {entry_id} not found for tenant {self.tenant_id}"
                )

            if category is not None:
                entry.category = category
            if title is not None:
                entry.title = title
            if content is not None:
                entry.content = content
            if is_active is not None:
                entry.is_active = is_active

            self.db.flush()
            self.db.refresh(entry)
            return entry
        except Exception as e:
            logger.error(
                "KBService.update_entry failed [id=%s, tenant=%s]: %s",
                entry_id,
                self.tenant_id,
                e,
            )
            raise

    def delete_entry(self, entry_id: uuid.UUID) -> bool:
        try:
            return self.repo.soft_delete_by_id_and_tenant(entry_id, self.tenant_id)
        except Exception as e:
            logger.error(
                "KBService.delete_entry failed [id=%s, tenant=%s]: %s",
                entry_id,
                self.tenant_id,
                e,
            )
            raise

    def search(
        self, query: str, top_k: int = 5, category: str | None = None
    ) -> list[dict[str, Any]]:
        try:
            return self.repo.search_fts(
                self.tenant_id, query, top_k=top_k, category=category
            )
        except Exception as e:
            logger.error(
                "KBService.search failed [tenant=%s, query=%s]: %s",
                self.tenant_id,
                query,
                e,
            )
            raise

    def get_categories(self, active_only: bool = True) -> list[str]:
        try:
            return self.repo.get_categories_by_tenant(
                self.tenant_id, active_only=active_only
            )
        except Exception as e:
            logger.error(
                "KBService.get_categories failed [tenant=%s]: %s", self.tenant_id, e
            )
            raise

    def count(self, category: str | None = None, active_only: bool = True) -> int:
        try:
            return self.repo.count_by_tenant(
                self.tenant_id, category=category, active_only=active_only
            )
        except Exception as e:
            logger.error("KBService.count failed [tenant=%s]: %s", self.tenant_id, e)
            raise
