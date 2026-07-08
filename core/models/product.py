from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from config.value_limits import (
    PRODUCT_MARGIN_MAX,
    PRODUCT_MARGIN_MIN,
    PRODUCT_MONEY_MAX,
    PRODUCT_MONEY_MIN,
    PRODUCT_STOCK_MAX,
    PRODUCT_STOCK_MIN,
    PRODUCT_TAX_MAX,
    PRODUCT_TAX_MIN,
)
from config.database import Base


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint(
            f"price IS NULL OR (price >= {PRODUCT_MONEY_MIN} AND price <= {PRODUCT_MONEY_MAX})",
            name="ck_products_price_range",
        ),
        CheckConstraint(
            f"stock >= {PRODUCT_STOCK_MIN} AND stock <= {PRODUCT_STOCK_MAX}",
            name="ck_products_stock_range",
        ),
        CheckConstraint(
            f"cost IS NULL OR (cost >= {PRODUCT_MONEY_MIN} AND cost <= {PRODUCT_MONEY_MAX})",
            name="ck_products_cost_range",
        ),
        CheckConstraint(
            f"margin IS NULL OR (margin >= {PRODUCT_MARGIN_MIN} AND margin <= {PRODUCT_MARGIN_MAX})",
            name="ck_products_margin_range",
        ),
        CheckConstraint(
            f"taxes IS NULL OR (taxes >= {PRODUCT_TAX_MIN} AND taxes <= {PRODUCT_TAX_MAX})",
            name="ck_products_taxes_range",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sku = Column(String(50), unique=True, nullable=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Numeric(10, 2), nullable=True)
    stock = Column(Integer, nullable=False, default=0)
    category = Column(String(100), nullable=True)
    is_available = Column(Boolean, nullable=False, default=True)
    cost = Column(Numeric(10, 2), nullable=True)
    margin = Column(Numeric(10, 2), nullable=True)
    provider = Column(String(100), nullable=True)
    taxes = Column(Numeric(5, 2), nullable=True, default=0.19)
    unit_of_measure = Column(String(20), nullable=True, default="un")
    format = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "sku": self.sku,
            "name": self.name,
            "description": self.description,
            "price": float(self.price) if self.price else None,
            "stock": self.stock,
            "category": self.category,
            "is_available": self.is_available,
            "cost": float(self.cost) if self.cost else None,
            "margin": float(self.margin) if self.margin else None,
            "provider": self.provider,
            "taxes": float(self.taxes) if self.taxes else None,
            "unit_of_measure": self.unit_of_measure,
            "format": self.format,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
