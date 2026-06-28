from __future__ import annotations

import logging
import uuid

from sqlalchemy import text
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

    def find_by_sku(self, sku: str) -> Product | None:
        try:
            return self.db.query(Product).filter(Product.sku == sku).first()
        except Exception as e:
            logger.error("ProductRepository.find_by_sku failed [sku=%s]: %s", sku, e)
            raise

    def search_by_name(
        self,
        query: str,
        limit: int = 20,
    ) -> list[Product]:
        try:
            sql = text("""
                SELECT id, sku, name, description, price, stock, category,
                       is_available, cost, margin, provider, taxes,
                       unit_of_measure, format, created_at, updated_at
                FROM products
                WHERE similarity(name, CAST(:query AS TEXT)) > 0.25
                   OR name ILIKE CAST(:ilike_query AS TEXT)
                ORDER BY similarity(name, CAST(:query AS TEXT)) DESC, name ASC
                LIMIT :limit
            """)
            result = self.db.execute(
                sql,
                {"query": query, "ilike_query": f"%{query}%", "limit": limit},
            )
            rows = result.mappings().all()
            return [
                Product(
                    id=row["id"],
                    sku=row["sku"],
                    name=row["name"],
                    description=row["description"],
                    price=row["price"],
                    stock=row["stock"],
                    category=row["category"],
                    is_available=row["is_available"],
                    cost=row["cost"],
                    margin=row["margin"],
                    provider=row["provider"],
                    taxes=row["taxes"],
                    unit_of_measure=row["unit_of_measure"],
                    format=row["format"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
                for row in rows
            ]
        except Exception as e:
            logger.error(
                "ProductRepository.search_by_name failed [query=%s]: %s",
                query,
                e,
            )
            raise

    def get_categories(self) -> list[str]:
        try:
            rows = (
                self.db.query(Product.category)
                .filter(Product.category.isnot(None))
                .distinct()
                .all()
            )
            return sorted(row[0] for row in rows)
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
