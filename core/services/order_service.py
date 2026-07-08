from __future__ import annotations

from datetime import datetime
import logging
import uuid
from decimal import Decimal
from sqlalchemy.orm import Session
from models.order import Order, OrderItem
from models.product import Product
from services.cart_service import CartService
from config.value_limits import (
    CART_QUANTITY_MAX,
    CART_QUANTITY_MIN,
    ensure_int_range,
)

logger = logging.getLogger(__name__)


class OrderService:
    ALLOWED_TRANSITIONS: dict[str, set[str]] = {
        "pending": {"confirmed", "cancelled"},
        "confirmed": {"preparing", "cancelled"},
        "preparing": {"ready", "cancelled"},
        "ready": {"delivered"},
        "delivered": set(),
        "cancelled": set(),
    }

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
                ensure_int_range(
                    cart_item.quantity,
                    name="Cantidad inválida o vacía en el carrito",
                    min_value=CART_QUANTITY_MIN,
                    max_value=CART_QUANTITY_MAX,
                )

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

            # Update order total and status to pending (awaiting operator pickup/confirmation)
            order.total_amount = total_amount
            order.status = "pending"

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

            # Validate state transition
            allowed = self.ALLOWED_TRANSITIONS.get(order.status, set())
            if status not in allowed:
                raise ValueError(
                    f"Invalid transition from '{order.status}' to '{status}'. "
                    f"Allowed: {sorted(allowed) if allowed else 'none (terminal state)'}"
                )

            # If transitioning to cancelled from pending/confirmed, restore stock
            if status == "cancelled" and order.status in ("pending", "confirmed"):
                for item in order.items:
                    product = (
                        self.db.query(Product)
                        .filter(Product.id == item.product_id)
                        .with_for_update()
                        .first()
                    )
                    if product:
                        product.stock += item.quantity
                        product.is_available = True

            order.status = status
            if status == "confirmed" and order.confirmed_at is None:
                order.confirmed_at = datetime.now()
            self.db.flush()
            self.db.refresh(order)
            return order
        except Exception as e:
            logger.error(
                "OrderService.update_order_status failed [id=%s]: %s", order_id, e
            )
            raise

    def get_attention_time_metrics(self) -> dict[str, int | None]:
        try:
            orders = self.db.query(Order).filter(Order.confirmed_at.isnot(None)).all()
            today = datetime.now().date()
            durations: list[int] = []
            for order in orders:
                if not order.created_at or not order.confirmed_at:
                    continue
                if order.confirmed_at.date() != today:
                    continue
                delta_minutes = int(
                    round((order.confirmed_at - order.created_at).total_seconds() / 60)
                )
                durations.append(max(delta_minutes, 0))

            if not durations:
                return {
                    "real_daily_average_minutes": None,
                    "confirmed_orders_count": 0,
                }

            average_minutes = int(round(sum(durations) / len(durations)))
            return {
                "real_daily_average_minutes": average_minutes,
                "confirmed_orders_count": len(durations),
            }
        except Exception as e:
            logger.error("OrderService.get_attention_time_metrics failed: %s", e)
            raise

    def cancel_order(self, order_id: uuid.UUID, user_id: int) -> Order:
        """Allows a user to cancel their own order only if it is still in 'pending' status, restoring product stock."""
        try:
            order = self.get_order(order_id)
            if not order:
                raise ValueError("Pedido no encontrado")
            if order.user_id != user_id:
                raise ValueError("No autorizado para cancelar este pedido")
            if order.status != "pending":
                raise ValueError("Solo se pueden cancelar pedidos en estado 'pending'")

            # Restore stock for each item
            for item in order.items:
                product = (
                    self.db.query(Product)
                    .filter(Product.id == item.product_id)
                    .with_for_update()
                    .first()
                )
                if product:
                    product.stock += item.quantity
                    product.is_available = True

            order.status = "cancelled"
            self.db.flush()
            self.db.refresh(order)
            logger.info("Order successfully cancelled by user [order_id=%s]", order.id)
            return order
        except Exception as e:
            logger.error(
                "OrderService.cancel_order failed [id=%s, user=%s]: %s",
                order_id,
                user_id,
                e,
            )
            raise
