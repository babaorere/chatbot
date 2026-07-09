from __future__ import annotations

from contextlib import nullcontext
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
from services.business_config_service import BusinessConfigService
from services.order_service import OrderService
from config.value_limits import CART_QUANTITY_MAX

logger = logging.getLogger(__name__)


def _raise_http_for_order_value_error(exc: ValueError) -> None:
    detail = str(exc)
    lowered = detail.lower()
    if "not found" in lowered or "no encontrado" in lowered:
        raise HTTPException(404, detail)
    if "not authorized" in lowered or "no autorizado" in lowered:
        raise HTTPException(403, detail)
    raise HTTPException(400, detail)

router = APIRouter(prefix="/orders", tags=["orders"])


# ── Request DTOs ─────────────────────────────────────────────────────────────


class CartAddRequest(BaseModel):
    user_id: str = Field(
        ..., description="ID externo del usuario en la plataforma (Telegram ID, etc)"
    )
    platform: str = Field(..., description="Plataforma del canal (ej: telegram)")
    product_id: uuid.UUID
    quantity: int = Field(default=1, ge=1, le=CART_QUANTITY_MAX)


class CartRemoveRequest(BaseModel):
    user_id: str
    platform: str
    product_id: uuid.UUID
    quantity: int | None = Field(default=None, ge=1, le=CART_QUANTITY_MAX)


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


class OrderCancelRequest(BaseModel):
    user_id: str = Field(..., description="ID del usuario en la plataforma")
    platform: str = Field(..., description="Plataforma de origen (ej: telegram)")


def build_checkout_confirmation_message(
    order: dict[str, Any], estimated_attention_minutes: int
) -> str:
    order_id = str(order.get("id", "")).strip()
    total_amount = order.get("total_amount")
    total_text = f"${float(total_amount):,.0f}" if total_amount is not None else "—"
    parts = [
        "Compra confirmada.",
        "",
        f"Pedido: {order_id or 'sin identificador'}",
        f"Total: {total_text}",
        f"Tiempo estimado de atención: {estimated_attention_minutes} minutos.",
        "Te avisaremos si hay algún cambio relevante.",
    ]
    return "\n".join(parts)


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/cart/add")
def add_to_cart(
    data: CartAddRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Agrega un producto al carrito activo del usuario y devuelve el estado actualizado."""
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
        _raise_http_for_order_value_error(e)
    except Exception as e:
        logger.error("add_to_cart endpoint failed: %s", e)
        raise HTTPException(500, "Failed to add item to cart")


@router.post("/cart/remove")
def remove_from_cart(
    data: CartRemoveRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Quita unidades de un producto del carrito activo del usuario."""
    try:
        user_svc = UserService(db)
        user = user_svc.get_or_create(external_id=data.user_id, platform=data.platform)

        cart_svc = CartService(db)
        with safe_transaction(db):
            cart = cart_svc.remove_from_cart(
                user_id=user.id, product_id=data.product_id, quantity=data.quantity
            )

        return {"status": "success", "cart": cart.to_dict()}
    except ValueError as e:
        _raise_http_for_order_value_error(e)
    except Exception as e:
        logger.error("remove_from_cart endpoint failed: %s", e)
        raise HTTPException(500, "Failed to remove item from cart")


@router.get("/cart")
def get_cart(
    user_id: str,
    platform: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Recupera el carrito actual de un usuario, creándolo si todavía no existe."""
    try:
        user_svc = UserService(db)
        user = user_svc.get_or_create(external_id=user_id, platform=platform)

        cart_svc = CartService(db)
        cart = cart_svc.get_or_create_cart(user_id=user.id)
        return cart.to_dict()
    except Exception as e:
        logger.error("get_cart endpoint failed: %s", e)
        raise HTTPException(500, "Failed to retrieve cart")


@router.post("/checkout")
def checkout(
    data: CheckoutRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Convierte el carrito activo en una orden validando stock y datos de entrega."""
    try:
        user_svc = UserService(db)
        user = user_svc.get_or_create(external_id=data.user_id, platform=data.platform)

        order_svc = OrderService(db)
        transaction = safe_transaction(db)
        if transaction is None:
            transaction = nullcontext()
        with transaction:
            order = order_svc.checkout_cart(
                user_id=user.id,
                session_id=data.session_id,
                delivery_address=data.delivery_address,
                payment_method=data.payment_method,
            )

        estimated_attention_minutes = (
            BusinessConfigService(db).get_config().estimated_attention_minutes
        )
        return {
            "status": "success",
            "order": order.to_dict(),
            "estimated_attention_minutes": estimated_attention_minutes,
            "customer_message": build_checkout_confirmation_message(
                order.to_dict(),
                estimated_attention_minutes,
            ),
        }
    except ValueError as e:
        _raise_http_for_order_value_error(e)
    except Exception as e:
        logger.error("checkout endpoint failed: %s", e)
        raise HTTPException(500, "Failed to place order")


@router.get("/{order_id}")
def get_order(
    order_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Recupera una orden específica por su identificador único."""
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
        raise HTTPException(500, "Failed to retrieve order")


@router.get("")
def list_orders(
    user_id: str,
    platform: str,
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Lista las órdenes asociadas al usuario identificado por canal y external ID."""
    try:
        user_svc = UserService(db)
        user = user_svc.get_or_create(external_id=user_id, platform=platform)

        order_svc = OrderService(db)
        orders = order_svc.list_user_orders(user.id)
        return [order.to_dict() for order in orders]
    except Exception as e:
        logger.error("list_orders endpoint failed: %s", e)
        raise HTTPException(500, "Failed to list orders")


@router.put("/{order_id}/status")
def update_order_status(
    order_id: uuid.UUID,
    data: OrderStatusUpdateRequest,
    db: Session = Depends(get_db),
    admin_key: str = Depends(get_admin_api_key),
) -> dict[str, Any]:
    """Actualiza el estado de una orden desde un endpoint administrativo protegido."""
    try:
        order_svc = OrderService(db)
        with safe_transaction(db):
            order = order_svc.update_order_status(order_id, data.status)
        return {"status": "success", "order": order.to_dict()}
    except ValueError as e:
        _raise_http_for_order_value_error(e)
    except Exception as e:
        logger.error("update_order_status endpoint failed: %s", e)
        raise HTTPException(500, "Failed to update order status")


@router.post("/{order_id}/cancel")
def cancel_order(
    order_id: uuid.UUID,
    data: OrderCancelRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Permite al cliente cancelar su propia orden mientras siga pendiente."""
    try:
        user_svc = UserService(db)
        user = user_svc.get_or_create(external_id=data.user_id, platform=data.platform)

        order_svc = OrderService(db)
        with safe_transaction(db):
            order = order_svc.cancel_order(order_id, user.id)

        return {"status": "success", "order": order.to_dict()}
    except ValueError as e:
        _raise_http_for_order_value_error(e)
    except Exception as e:
        logger.error("cancel_order endpoint failed [order_id=%s]: %s", order_id, e)
        raise HTTPException(500, "Failed to cancel order")
