from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from models.product import Product
from repositories.product_repository import ProductRepository

logger = logging.getLogger(__name__)


class ProductService:
    def __init__(self, db: Session, tenant_id: uuid.UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.repo = ProductRepository(db)

    def list_products(
        self,
        category: str | None = None,
        available_only: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Product]:
        try:
            return self.repo.find_by_tenant_id(
                self.tenant_id,
                category=category,
                available_only=available_only,
                skip=skip,
                limit=limit,
            )
        except Exception as e:
            logger.error(
                "ProductService.list_products failed [tenant=%s]: %s", self.tenant_id, e
            )
            raise

    def get_product(self, product_id: uuid.UUID) -> Product | None:
        try:
            return self.repo.find_by_id_and_tenant(product_id, self.tenant_id)
        except Exception as e:
            logger.error(
                "ProductService.get_product failed [id=%s, tenant=%s]: %s",
                product_id,
                self.tenant_id,
                e,
            )
            raise

    def create_product(
        self,
        name: str,
        description: str | None = None,
        price: float | None = None,
        stock: int = 0,
        category: str | None = None,
        is_available: bool = True,
    ) -> Product:
        try:
            product = Product(
                tenant_id=self.tenant_id,
                name=name,
                description=description,
                price=price,
                stock=stock,
                category=category,
                is_available=is_available,
            )
            return self.repo.save(product)
        except Exception as e:
            logger.error(
                "ProductService.create_product failed [tenant=%s, name=%s]: %s",
                self.tenant_id,
                name,
                e,
            )
            raise

    def update_product(
        self,
        product_id: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
        price: float | None = None,
        stock: int | None = None,
        category: str | None = None,
        is_available: bool | None = None,
    ) -> Product:
        try:
            product = self.repo.find_by_id_and_tenant(product_id, self.tenant_id)
            if not product:
                raise ValueError(
                    f"Product {product_id} not found for tenant {self.tenant_id}"
                )

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

            self.db.flush()
            self.db.refresh(product)
            return product
        except Exception as e:
            logger.error(
                "ProductService.update_product failed [id=%s, tenant=%s]: %s",
                product_id,
                self.tenant_id,
                e,
            )
            raise

    def delete_product(self, product_id: uuid.UUID) -> bool:
        try:
            product = self.repo.find_by_id_and_tenant(product_id, self.tenant_id)
            if not product:
                return False
            self.db.delete(product)
            self.db.flush()
            return True
        except Exception as e:
            logger.error(
                "ProductService.delete_product failed [id=%s, tenant=%s]: %s",
                product_id,
                self.tenant_id,
                e,
            )
            raise

    def search(self, query: str, limit: int = 20) -> list[Product]:
        try:
            return self.repo.search_by_name(self.tenant_id, query, limit=limit)
        except Exception as e:
            logger.error(
                "ProductService.search failed [tenant=%s, query=%s]: %s",
                self.tenant_id,
                query,
                e,
            )
            raise

    def get_categories(self) -> list[str]:
        try:
            return self.repo.get_categories_by_tenant(self.tenant_id)
        except Exception as e:
            logger.error(
                "ProductService.get_categories failed [tenant=%s]: %s",
                self.tenant_id,
                e,
            )
            raise

    def count(self, category: str | None = None, available_only: bool = False) -> int:
        try:
            return self.repo.count_by_tenant(
                self.tenant_id, category=category, available_only=available_only
            )
        except Exception as e:
            logger.error(
                "ProductService.count failed [tenant=%s]: %s", self.tenant_id, e
            )
            raise
