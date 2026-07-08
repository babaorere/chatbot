from __future__ import annotations

import uuid
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from config.database import Base
from config.value_limits import CART_QUANTITY_MAX, CART_QUANTITY_MIN


class Cart(Base):
    __tablename__ = "carts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", backref="cart")
    items = relationship(
        "CartItem", back_populates="cart", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "items": [item.to_dict() for item in self.items],
        }


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        CheckConstraint(
            f"quantity >= {CART_QUANTITY_MIN} AND quantity <= {CART_QUANTITY_MAX}",
            name="ck_cart_items_quantity_range",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cart_id = Column(
        UUID(as_uuid=True), ForeignKey("carts.id", ondelete="CASCADE"), nullable=False
    )
    product_id = Column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    quantity = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    cart = relationship("Cart", back_populates="items")
    product = relationship("Product")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "cart_id": str(self.cart_id),
            "product_id": str(self.product_id),
            "product_name": self.product.name if self.product else None,
            "product_price": float(self.product.price)
            if self.product and self.product.price
            else 0.0,
            "quantity": self.quantity,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
