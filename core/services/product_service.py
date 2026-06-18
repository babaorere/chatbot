from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from models.product import Product
from repositories.product_repository import ProductRepository

logger = logging.getLogger(__name__)


class ProductService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ProductRepository(db)

    def list_products(
        self,
        category: str | None = None,
        available_only: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Product]:
        try:
            return self.repo.find_all(
                category=category,
                available_only=available_only,
                skip=skip,
                limit=limit,
            )
        except Exception as e:
            logger.error("ProductService.list_products failed: %s", e)
            raise

    def get_product(self, product_id: uuid.UUID) -> Product | None:
        try:
            return self.repo.find_by_id(product_id)
        except Exception as e:
            logger.error(
                "ProductService.get_product failed [id=%s]: %s",
                product_id,
                e,
            )
            raise

    def create_product(
        self,
        name: str,
        sku: str | None = None,
        description: str | None = None,
        price: float | None = None,
        stock: int = 0,
        category: str | None = None,
        is_available: bool = True,
        cost: float | None = None,
        margin: float | None = None,
        provider: str | None = None,
        taxes: float | None = 0.19,
        unit_of_measure: str | None = "un",
    ) -> Product:
        try:
            product = Product(
                sku=sku,
                name=name,
                description=description,
                price=price,
                stock=stock,
                category=category,
                is_available=is_available,
                cost=cost,
                margin=margin,
                provider=provider,
                taxes=taxes,
                unit_of_measure=unit_of_measure,
            )
            return self.repo.save(product)
        except Exception as e:
            logger.error(
                "ProductService.create_product failed [name=%s]: %s",
                name,
                e,
            )
            raise

    def update_product(
        self,
        product_id: uuid.UUID,
        sku: str | None = None,
        name: str | None = None,
        description: str | None = None,
        price: float | None = None,
        stock: int | None = None,
        category: str | None = None,
        is_available: bool | None = None,
        cost: float | None = None,
        margin: float | None = None,
        provider: str | None = None,
        taxes: float | None = None,
        unit_of_measure: str | None = None,
    ) -> Product:
        try:
            product = self.repo.find_by_id(product_id)
            if not product:
                raise ValueError(f"Product {product_id} not found")

            if sku is not None:
                product.sku = sku
            if name is not None:
                product.name = name
            if description is not None:
                product.description = description
            if price is not None:
                product.price = price
            if stock is not None:
                product.stock = stock
            if category is not None:
                product.category = category
            if is_available is not None:
                product.is_available = is_available
            if cost is not None:
                product.cost = cost
            if margin is not None:
                product.margin = margin
            if provider is not None:
                product.provider = provider
            if taxes is not None:
                product.taxes = taxes
            if unit_of_measure is not None:
                product.unit_of_measure = unit_of_measure

            self.db.flush()
            self.db.refresh(product)
            return product
        except Exception as e:
            logger.error(
                "ProductService.update_product failed [id=%s]: %s",
                product_id,
                e,
            )
            raise

    def delete_product(self, product_id: uuid.UUID) -> bool:
        try:
            product = self.repo.find_by_id(product_id)
            if not product:
                return False
            self.db.delete(product)
            self.db.flush()
            return True
        except Exception as e:
            logger.error(
                "ProductService.delete_product failed [id=%s]: %s",
                product_id,
                e,
            )
            raise

    def search(self, query: str, limit: int = 20) -> list[Product]:
        try:
            return self.repo.search_by_name(query, limit=limit)
        except Exception as e:
            logger.error(
                "ProductService.search failed [query=%s]: %s",
                query,
                e,
            )
            raise

    def get_categories(self) -> list[str]:
        try:
            return self.repo.get_categories()
        except Exception as e:
            logger.error("ProductService.get_categories failed: %s", e)
            raise

    def count(self, category: str | None = None, available_only: bool = False) -> int:
        try:
            return self.repo.count_all(category=category, available_only=available_only)
        except Exception as e:
            logger.error("ProductService.count failed: %s", e)
            raise
