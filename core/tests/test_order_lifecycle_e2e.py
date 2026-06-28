from __future__ import annotations

import pytest

from services.user_service import UserService
from services.product_service import ProductService
from services.cart_service import CartService
from services.order_service import OrderService


@pytest.mark.asyncio
async def test_order_lifecycle_e2e_conversational_flow(db_session):
    """Prueba E2E del ciclo de vida de un pedido: interactúa con el carrito, realiza checkout, confirma y cancela, verificando el stock en BD."""
    # 1. Registrar usuario y poblar productos
    user_svc = UserService(db_session)
    user = user_svc.get_or_create(external_id="telegram_e2e_user_1", platform="telegram", display_name="Test E2E")
    
    product_svc = ProductService(db_session)
    pisco = product_svc.create_product(
        sku="PISCO-ALTO-CARMEN",
        name="Alto del Carmen 35°",
        price=6500.0,
        stock=10,
        category="pisco",
    )
    assert pisco.id is not None

    # 2. Agregar productos al carro del usuario (Carrito persistente en PostgreSQL)
    cart_svc = CartService(db_session)
    cart_svc.add_to_cart(user_id=user.id, product_id=pisco.id, quantity=3)

    cart = cart_svc.get_or_create_cart(user.id)
    assert len(cart.items) == 1
    assert cart.items[0].quantity == 3

    # 3. Realizar el Checkout del Pedido (Pasa del carro de compras a Orden Pendiente)
    order_svc = OrderService(db_session)
    order = order_svc.checkout_cart(
        user_id=user.id,
        session_id="session-e2e-abc",
        delivery_address="Providencia 1234, Santiago",
        payment_method="transferencia",
    )

    # 4. Validaciones de la Orden y Reserva de Stock
    assert order.id is not None
    assert order.status == "pending"
    assert float(order.total_amount) == 19500.0  # 3 * 6500.0

    # Stock disminuido en 3
    db_session.refresh(pisco)
    assert pisco.stock == 7

    # Carro vacío tras checkout
    cart_after = cart_svc.get_or_create_cart(user.id)
    assert len(cart_after.items) == 0

    # 5. El operador confirma el pedido
    order_svc.update_order_status(order.id, "confirmed")
    assert order.status == "confirmed"
    
    # El stock sigue reservado/disminuido
    db_session.refresh(pisco)
    assert pisco.stock == 7

    # 6. Cancelación del pedido (Restauración de stock)
    # Cambiamos estado de confirmed a cancelled para validar la reposición
    order_svc.update_order_status(order.id, "cancelled")
    assert order.status == "cancelled"

    # El stock debe retornar a 10
    db_session.refresh(pisco)
    assert pisco.stock == 10
