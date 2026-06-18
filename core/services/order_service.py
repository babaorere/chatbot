from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from sqlalchemy.orm import Session
from models.order import Order, OrderItem
from models.product import Product
from services.cart_service import CartService

logger = logging.getLogger(__name__)


class OrderService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.cart_svc = CartService(db)

    def get_order(self, order_id: uuid.UUID) -> Order | None:
        try:
            return self.db.query(Order).filter(Order.id == order_id).first()
        except Exception as e:
            logger.error("OrderService.get_order failed [id=%s]: %s", order_id, e)
            raise

    def list_user_orders(self, user_id: int) -> list[Order]:
        try:
            return (
                self.db.query(Order)
                .filter(Order.user_id == user_id)
                .order_by(Order.created_at.desc())
                .all()
            )
        except Exception as e:
            logger.error(
                "OrderService.list_user_orders failed [user_id=%s]: %s", user_id, e
            )
            raise

    def checkout_cart(
        self,
        user_id: int,
        session_id: str | None = None,
        delivery_address: str | None = None,
        payment_method: str | None = None,
    ) -> Order:
        """Converts user's cart to a persistent Order with transaction-safe stock checking and locking."""
        try:
            cart = self.cart_svc.get_or_create_cart(user_id)
            if not cart.items:
                raise ValueError("Cannot checkout an empty cart")

            # Initialize variables
            order_items: list[OrderItem] = []
            total_amount = Decimal("0.0")

            # Create the order first (in pending status)
            order = Order(
                user_id=user_id,
                session_id=session_id,
                status="pending",
                delivery_address=delivery_address,
                payment_method=payment_method,
            )
            self.db.add(order)
            self.db.flush()

            # Reserve stock under pessimistic lock (with_for_update) for each product
            for cart_item in cart.items:
                # 1. Lock product row to prevent concurrency issues
                product = (
                    self.db.query(Product)
                    .filter(Product.id == cart_item.product_id)
                    .with_for_update()
                    .first()
                )

                if not product:
                    raise ValueError(
                        f"Product {cart_item.product_name} no longer exists"
                    )

                if not product.is_available:
                    raise ValueError(f"Product {product.name} is no longer available")

                if product.stock < cart_item.quantity:
                    raise ValueError(
                        f"Stock insuficiente para '{product.name}'. Solicitado: {cart_item.quantity}, disponible: {product.stock}"
                    )

                # 2. Decrement stock
                product.stock -= cart_item.quantity
                if product.stock == 0:
                    product.is_available = False

                # 3. Calculate prices
                price = product.price or Decimal("0.0")
                item_total = price * cart_item.quantity
                total_amount += item_total

                # 4. Create OrderItem
                order_item = OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    quantity=cart_item.quantity,
                    unit_price=price,
                    total_price=item_total,
                )
                order_items.append(order_item)
                self.db.add(order_item)

            # Update order total and status to confirmed (since stock is successfully reserved)
            order.total_amount = total_amount
            order.status = "confirmed"

            # 5. Clear the cart
            self.cart_svc.clear_cart(user_id)

            self.db.flush()
            self.db.refresh(order)

            logger.info(
                "Order successfully created and stock reserved [order_id=%s, total=%s]",
                order.id,
                total_amount,
            )
            return order
        except Exception as e:
            logger.error(
                "OrderService.checkout_cart failed [user_id=%s]: %s", user_id, e
            )
            raise

    def update_order_status(self, order_id: uuid.UUID, status: str) -> Order:
        try:
            order = self.get_order(order_id)
            if not order:
                raise ValueError("Order not found")
            order.status = status
            self.db.flush()
            self.db.refresh(order)
            return order
        except Exception as e:
            logger.error(
                "OrderService.update_order_status failed [id=%s]: %s", order_id, e
            )
            raise
