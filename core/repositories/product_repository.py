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

    def find_all(
        self,
        category: str | None = None,
        available_only: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Product]:
        try:
            query = self.db.query(Product)
            if category:
                query = query.filter(Product.category == category)
            if available_only:
                query = query.filter(Product.is_available)
            return query.order_by(Product.name).offset(skip).limit(limit).all()
        except Exception as e:
            logger.error("ProductRepository.find_all failed: %s", e)
            raise

    def find_by_id(
        self,
        product_id: uuid.UUID,
    ) -> Product | None:
        try:
            return self.db.query(Product).filter(Product.id == product_id).first()
        except Exception as e:
            logger.error(
                "ProductRepository.find_by_id failed [id=%s]: %s",
                product_id,
                e,
            )
            raise

    def search_by_name(
        self,
        query: str,
        limit: int = 20,
    ) -> list[Product]:
        try:
            return (
                self.db.query(Product)
                .filter(Product.name.ilike(f"%{query}%"))
                .order_by(Product.name)
                .limit(limit)
                .all()
            )
        except Exception as e:
            logger.error(
                "ProductRepository.search_by_name failed [query=%s]: %s",
                query,
                e,
            )
            raise

    def get_categories(self) -> list[str]:
        try:
            return sorted(
                list(
                    self.db.query(Product.category)
                    .filter(Product.category.isnot(None))
                    .distinct()
                    .pluck("category")
                )
            )
        except Exception as e:
            logger.error("ProductRepository.get_categories failed: %s", e)
            raise

    def count_all(
        self,
        category: str | None = None,
        available_only: bool = False,
    ) -> int:
        try:
            query = self.db.query(Product)
            if category:
                query = query.filter(Product.category == category)
            if available_only:
                query = query.filter(Product.is_available)
            return query.count()
        except Exception as e:
            logger.error("ProductRepository.count_all failed: %s", e)
            raise
