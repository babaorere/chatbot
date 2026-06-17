from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from models.product import Product
from repositories.base import JpaRepository

logger = logging.getLogger(__name__)


class ProductRepository(JpaRepository[Product]):
    def __init__(self, db: Session) -> None:
        super().__init__(Product, db)

    def find_by_tenant_id(
        self,
        tenant_id: uuid.UUID,
        category: str | None = None,
        available_only: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Product]:
        try:
            query = self.db.query(Product).filter(Product.tenant_id == tenant_id)
            if category:
                query = query.filter(Product.category == category)
            if available_only:
                query = query.filter(Product.is_available)
            return query.order_by(Product.name).offset(skip).limit(limit).all()
        except Exception as e:
            logger.error(
                "ProductRepository.find_by_tenant_id failed [tenant=%s]: %s",
                tenant_id,
                e,
            )
            raise

    def find_by_id_and_tenant(
        self,
        product_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> Product | None:
        try:
            return (
                self.db.query(Product)
                .filter(Product.id == product_id, Product.tenant_id == tenant_id)
                .first()
            )
        except Exception as e:
            logger.error(
                "ProductRepository.find_by_id_and_tenant failed [id=%s, tenant=%s]: %s",
                product_id,
                tenant_id,
                e,
            )
            raise

    def search_by_name(
        self,
        tenant_id: uuid.UUID,
        query: str,
        limit: int = 20,
    ) -> list[Product]:
        try:
            return (
                self.db.query(Product)
                .filter(
                    Product.tenant_id == tenant_id,
                    Product.name.ilike(f"%{query}%"),
                )
                .order_by(Product.name)
                .limit(limit)
                .all()
            )
        except Exception as e:
            logger.error(
                "ProductRepository.search_by_name failed [tenant=%s, query=%s]: %s",
                tenant_id,
                query,
                e,
            )
            raise

    def get_categories_by_tenant(
        self,
        tenant_id: uuid.UUID,
    ) -> list[str]:
        try:
            return sorted(
                list(
                    self.db.query(Product.category)
                    .filter(
                        Product.tenant_id == tenant_id, Product.category.isnot(None)
                    )
                    .distinct()
                    .pluck("category")
                )
            )
        except Exception as e:
            logger.error(
                "ProductRepository.get_categories_by_tenant failed [tenant=%s]: %s",
                tenant_id,
                e,
            )
            raise

    def count_by_tenant(
        self,
        tenant_id: uuid.UUID,
        category: str | None = None,
        available_only: bool = False,
    ) -> int:
        try:
            query = self.db.query(Product).filter(Product.tenant_id == tenant_id)
            if category:
                query = query.filter(Product.category == category)
            if available_only:
                query = query.filter(Product.is_available)
            return query.count()
        except Exception as e:
            logger.error(
                "ProductRepository.count_by_tenant failed [tenant=%s]: %s", tenant_id, e
            )
            raise
