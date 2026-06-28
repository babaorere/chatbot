from __future__ import annotations

import logging
import uuid
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from config.database import get_db, safe_transaction
from app.security import get_admin_api_key
from services.user_service import UserService
from services.cart_service import CartService
from services.order_service import OrderService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orders", tags=["orders"])


# ── Request DTOs ─────────────────────────────────────────────────────────────


class CartAddRequest(BaseModel):
    user_id: str = Field(
        ..., description="ID externo del usuario en la plataforma (Telegram ID, etc)"
    )
    platform: str = Field(..., description="Plataforma del canal (ej: telegram)")
    product_id: uuid.UUID
    quantity: int = Field(default=1, ge=1)


class CartRemoveRequest(BaseModel):
    user_id: str
    platform: str
    product_id: uuid.UUID
    quantity: int | None = Field(default=None, ge=1)


class CheckoutRequest(BaseModel):
    user_id: str
    platform: str
    session_id: str | None = None
    delivery_address: str | None = None
    payment_method: str | None = None  # cash, transfer, webpay


class OrderStatusUpdateRequest(BaseModel):
    status: str = Field(
        ..., description="Nuevo estado: pending, confirmed, cancelled, delivered"
    )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/cart/add")
def add_to_cart(
    data: CartAddRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        user_svc = UserService(db)
        user = user_svc.get_or_create(external_id=data.user_id, platform=data.platform)

        cart_svc = CartService(db)
        with safe_transaction(db):
            cart = cart_svc.add_to_cart(
                user_id=user.id, product_id=data.product_id, quantity=data.quantity
            )

        return {"status": "success", "cart": cart.to_dict()}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("add_to_cart endpoint failed: %s", e)
        raise HTTPException(500, f"Failed to add item to cart: {e}")


@router.post("/cart/remove")
def remove_from_cart(
    data: CartRemoveRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        user_svc = UserService(db)
        user = user_svc.get_or_create(external_id=data.user_id, platform=data.platform)

        cart_svc = CartService(db)
        with safe_transaction(db):
            cart = cart_svc.remove_from_cart(
                user_id=user.id, product_id=data.product_id, quantity=data.quantity
            )

        return {"status": "success", "cart": cart.to_dict()}
    except Exception as e:
        logger.error("remove_from_cart endpoint failed: %s", e)
        raise HTTPException(500, f"Failed to remove item from cart: {e}")


@router.get("/cart")
def get_cart(
    user_id: str,
    platform: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        user_svc = UserService(db)
        user = user_svc.get_or_create(external_id=user_id, platform=platform)

        cart_svc = CartService(db)
        cart = cart_svc.get_or_create_cart(user_id=user.id)
        return cart.to_dict()
    except Exception as e:
        logger.error("get_cart endpoint failed: %s", e)
        raise HTTPException(500, f"Failed to retrieve cart: {e}")


@router.post("/checkout")
def checkout(
    data: CheckoutRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        user_svc = UserService(db)
        user = user_svc.get_or_create(external_id=data.user_id, platform=data.platform)

        order_svc = OrderService(db)
        with safe_transaction(db):
            order = order_svc.checkout_cart(
                user_id=user.id,
                session_id=data.session_id,
                delivery_address=data.delivery_address,
                payment_method=data.payment_method,
            )

        return {"status": "success", "order": order.to_dict()}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("checkout endpoint failed: %s", e)
        raise HTTPException(500, f"Failed to place order: {e}")


@router.get("/{order_id}")
def get_order(
    order_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        order_svc = OrderService(db)
        order = order_svc.get_order(order_id)
        if not order:
            raise HTTPException(404, "Order not found")
        return order.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_order endpoint failed: %s", e)
        raise HTTPException(500, f"Failed to retrieve order: {e}")


@router.get("")
def list_orders(
    user_id: str,
    platform: str,
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    try:
        user_svc = UserService(db)
        user = user_svc.get_or_create(external_id=user_id, platform=platform)

        order_svc = OrderService(db)
        orders = order_svc.list_user_orders(user.id)
        return [order.to_dict() for order in orders]
    except Exception as e:
        logger.error("list_orders endpoint failed: %s", e)
        raise HTTPException(500, f"Failed to list orders: {e}")


@router.put("/{order_id}/status")
def update_order_status(
    order_id: uuid.UUID,
    data: OrderStatusUpdateRequest,
    db: Session = Depends(get_db),
    admin_key: str = Depends(get_admin_api_key),
) -> dict[str, Any]:
    """Secured admin endpoint to update the status of an order."""
    try:
        order_svc = OrderService(db)
        with safe_transaction(db):
            order = order_svc.update_order_status(order_id, data.status)
        return {"status": "success", "order": order.to_dict()}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("update_order_status endpoint failed: %s", e)
        raise HTTPException(500, f"Failed to update order status: {e}")
