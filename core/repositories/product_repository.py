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
            from sqlalchemy import text
            
            # Detect dialect to support SQLite/Mock fallback for tests
            is_sqlite = True
            try:
                dialect_name = self.db.bind.dialect.name
                if isinstance(dialect_name, str) and dialect_name != "sqlite":
                    is_sqlite = False
            except Exception:
                pass

            if is_sqlite:
                return (
                    self.db.query(Product)
                    .filter(Product.name.like(f"%{query}%"))
                    .order_by(Product.name)
                    .limit(limit)
                    .all()
                )

            # PostgreSQL trigram similarity query
            sql = text("""
                SELECT id, sku, name, description, price, stock, category, is_available, cost, margin, provider, taxes, unit_of_measure, created_at, updated_at
                FROM products
                WHERE similarity(name, :query) > 0.25 OR name ILIKE :ilike_query
                ORDER BY similarity(name, :query) DESC, name ASC
                LIMIT :limit
            """)
            result = self.db.execute(sql, {"query": query, "ilike_query": f"%{query}%", "limit": limit})
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
                    created_at=row["created_at"],
                    updated_at=row["updated_at"]
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
