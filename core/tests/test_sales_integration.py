from __future__ import annotations

import pytest
from services.user_service import UserService
from services.product_service import ProductService
from services.cart_service import CartService
from services.order_service import OrderService
from controllers import telegram_controller


def test_complete_sales_workflow(db_session):
    # 1. Create a user
    user_svc = UserService(db_session)
    user = user_svc.get_or_create(
        external_id="telegram_123", platform="telegram", display_name="Test Client"
    )
    assert user.id is not None

    # 2. Create products with initial stock
    product_svc = ProductService(db_session)
    pisco = product_svc.create_product(
        sku="PISCO-CONTROL-35",
        name="Pisco Control 35°",
        description="Pisco nacional de 35 grados",
        price=7990.00,
        stock=10,
        category="pisco",
        unit_of_measure="botella",
    )
    coca_cola = product_svc.create_product(
        sku="COCA-COLA-15L",
        name="Coca Cola 1.5L",
        description="Bebida gaseosa",
        price=1500.00,
        stock=20,
        category="bebida",
        unit_of_measure="botella",
    )
    assert pisco.id is not None
    assert coca_cola.id is not None

    # 3. Search product (as the bot does in root_agent)
    search_results = product_svc.search("pisco")
    assert len(search_results) == 1
    assert search_results[0].sku == "PISCO-CONTROL-35"

    # 4. Add items to cart
    cart_svc = CartService(db_session)
    cart_svc.add_to_cart(user_id=user.id, product_id=pisco.id, quantity=2)
    cart_svc.add_to_cart(user_id=user.id, product_id=coca_cola.id, quantity=3)

    # Verify cart contents
    cart = cart_svc.get_or_create_cart(user.id)
    assert len(cart.items) == 2
    assert cart.items[0].quantity == 2
    assert cart.items[1].quantity == 3

    # 5. Checkout (Order creation + Stock reservation)
    order_svc = OrderService(db_session)
    order = order_svc.checkout_cart(
        user_id=user.id,
        session_id="session_abc",
        delivery_address="Av. Providencia 1234",
        payment_method="transfer",
    )

    # 6. Verify order details
    assert order.id is not None
    assert order.status == "pending"
    order_svc.update_order_status(order.id, "confirmed")
    assert order.status == "confirmed"
    assert order.session_id == "session_abc"
    assert order.delivery_address == "Av. Providencia 1234"
    assert order.payment_method == "transfer"

    # Check total amount (2 * 7990 + 3 * 1500 = 15980 + 4500 = 20480)
    assert float(order.total_amount) == 20480.0

    # 7. Verify stock decremented correctly
    db_session.refresh(pisco)
    db_session.refresh(coca_cola)
    assert pisco.stock == 8
    assert coca_cola.stock == 17

    # 8. Verify cart is cleared
    cart_after = cart_svc.get_or_create_cart(user.id)
    assert len(cart_after.items) == 0


def test_checkout_insufficient_stock(db_session):
    user_svc = UserService(db_session)
    user = user_svc.get_or_create(external_id="telegram_456", platform="telegram")

    product_svc = ProductService(db_session)
    whisky = product_svc.create_product(
        sku="WHISKY-JW-BLACK",
        name="Johnnie Walker Black Label",
        price=24990.0,
        stock=1,
        category="whisky",
    )

    # Add 2 whiskies to cart when only 1 is in stock
    cart_svc = CartService(db_session)
    cart_svc.add_to_cart(user_id=user.id, product_id=whisky.id, quantity=2)

    order_svc = OrderService(db_session)

    # Checkout should fail with ValueError due to insufficient stock
    with pytest.raises(ValueError, match="Stock insuficiente"):
        order_svc.checkout_cart(user_id=user.id)

    # Ensure stock was NOT decremented (transaction rollback)
    db_session.refresh(whisky)
    assert whisky.stock == 1


def test_checkout_uses_db_stock_when_catalog_cache_is_stale(db_session):
    # Arrange
    user = UserService(db_session).get_or_create(
        external_id="telegram_cache_stale", platform="telegram"
    )
    product = ProductService(db_session).create_product(
        sku="CACHE-STALE-STOCK",
        name="Producto Stock DB",
        price=1990.0,
        stock=1,
        category="General",
    )
    CartService(db_session).add_to_cart(
        user_id=user.id,
        product_id=product.id,
        quantity=2,
    )
    previous_snapshot = telegram_controller._catalog_snapshot
    telegram_controller._catalog_snapshot = telegram_controller.CatalogSnapshot(
        products_by_id={
            str(product.id): {
                "id": str(product.id),
                "name": product.name,
                "price": 1990.0,
                "stock": 99,
                "category": "General",
                "is_available": True,
                "unit_of_measure": "un",
            }
        },
        version=999,
    )

    try:
        # Act / Assert
        with pytest.raises(ValueError, match="Stock insuficiente"):
            OrderService(db_session).checkout_cart(user_id=user.id)
    finally:
        telegram_controller._catalog_snapshot = previous_snapshot

    db_session.refresh(product)
    assert product.stock == 1
