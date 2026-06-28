from __future__ import annotations

import uuid

from sqlalchemy import Column, String, DateTime, Text, Integer, Numeric, Boolean, func
from sqlalchemy.dialects.postgresql import UUID
from config.database import Base


class Product(Base):
    __tablename__ = "products"

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
