from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def reset_business_config_snapshot() -> None:
    from controllers import telegram_controller

    telegram_controller._business_config_snapshot = (
        telegram_controller.BusinessConfigSnapshot()
    )


def test_promotions_text_uses_configured_products() -> None:
    db_mock = MagicMock()
    db_mock.query.return_value.filter.return_value.all.return_value = [
        SimpleNamespace(
            id="p1", name="Promo Uno", price=1200, stock=5, is_available=True
        ),
        SimpleNamespace(
            id="p2", name="Promo Dos", price=1500, stock=3, is_available=True
        ),
    ]
    config = SimpleNamespace(
        promotions_config={
            "enabled": True,
            "title": "Promociones de hoy",
            "mode": "manual",
            "product_ids": ["p1", "p2"],
        }
    )

    with (
        patch("controllers.telegram_controller.SessionLocal", return_value=db_mock),
        patch(
            "controllers.telegram_controller.BusinessConfigService"
        ) as config_service_mock,
    ):
        config_service_mock.return_value.get_config.return_value = config
        from controllers.telegram_controller import _get_promotions_text

        text, _ = _get_promotions_text()

    assert "Promociones de hoy" in text
    assert "Promo Uno" in text
    assert "Promo Dos" in text


def test_promotions_text_cache_hit_disabled_section_does_not_query_db() -> None:
    from controllers import telegram_controller
    from controllers.telegram_controller import _get_promotions_text

    telegram_controller.prime_business_config_cache(
        SimpleNamespace(
            human_agent_available=True,
            promotions_config={
                "enabled": False,
                "title": "Promos pausadas",
                "mode": "manual",
                "product_ids": [],
            },
            best_sellers_config={},
            favorites_config={},
        )
    )

    with (
        patch("controllers.telegram_controller.SessionLocal") as session_mock,
        patch(
            "controllers.telegram_controller.BusinessConfigService"
        ) as config_service_mock,
    ):
        text, product_names = _get_promotions_text()

    session_mock.assert_not_called()
    config_service_mock.assert_not_called()
    assert product_names == []
    assert "Promos pausadas" in text


def test_promotions_text_uses_catalog_cache_without_db_lookup() -> None:
    from controllers import telegram_controller
    from controllers.telegram_controller import _get_promotions_text

    telegram_controller._catalog_snapshot = telegram_controller.CatalogSnapshot(
        products_by_id={
            "p-cache": {
                "id": "p-cache",
                "name": "Promo Cacheada",
                "price": 1990.0,
                "stock": 9,
                "is_available": True,
            }
        },
        version=1,
    )
    telegram_controller.prime_business_config_cache(
        SimpleNamespace(
            human_agent_available=True,
            promotions_config={
                "enabled": True,
                "title": "Promos cache",
                "mode": "manual",
                "product_ids": ["p-cache"],
            },
            best_sellers_config={},
            favorites_config={},
        )
    )

    with patch("controllers.telegram_controller.SessionLocal") as session_mock:
        text, product_names = _get_promotions_text()

    session_mock.assert_not_called()
    assert product_names == ["Promo Cacheada"]
    assert "Promos cache" in text
    assert "Promo Cacheada" in text


def test_best_sellers_text_uses_manual_selection_when_configured() -> None:
    db_mock = MagicMock()
    db_mock.query.return_value.filter.return_value.all.return_value = [
        SimpleNamespace(
            id="b1", name="Más Uno", price=2200, stock=8, is_available=True
        ),
        SimpleNamespace(
            id="b2", name="Más Dos", price=2600, stock=4, is_available=True
        ),
    ]
    config = SimpleNamespace(
        best_sellers_config={
            "enabled": True,
            "title": "Más vendidos",
            "mode": "manual",
            "product_ids": ["b1", "b2"],
        }
    )

    with (
        patch("controllers.telegram_controller.SessionLocal", return_value=db_mock),
        patch(
            "controllers.telegram_controller.BusinessConfigService"
        ) as config_service_mock,
    ):
        config_service_mock.return_value.get_config.return_value = config
        from controllers.telegram_controller import _get_best_sellers_text

        text, _ = _get_best_sellers_text()

    assert "Más vendidos" in text
    assert "Más Uno" in text
    assert "Más Dos" in text


def test_best_sellers_manual_text_uses_catalog_cache_without_db_lookup() -> None:
    from controllers import telegram_controller
    from controllers.telegram_controller import _get_best_sellers_text

    telegram_controller._catalog_snapshot = telegram_controller.CatalogSnapshot(
        products_by_id={
            "b-cache": {
                "id": "b-cache",
                "name": "Más Cacheado",
                "price": 3990.0,
                "stock": 4,
                "is_available": True,
            }
        },
        version=1,
    )
    telegram_controller.prime_business_config_cache(
        SimpleNamespace(
            human_agent_available=True,
            promotions_config={},
            best_sellers_config={
                "enabled": True,
                "title": "Más cache",
                "mode": "manual",
                "product_ids": ["b-cache"],
            },
            favorites_config={},
        )
    )

    with patch("controllers.telegram_controller.SessionLocal") as session_mock:
        text, product_names = _get_best_sellers_text()

    session_mock.assert_not_called()
    assert product_names == ["Más Cacheado"]
    assert "Más cache" in text
    assert "Más Cacheado" in text


def test_favorites_text_uses_configured_products() -> None:
    db_mock = MagicMock()
    db_mock.query.return_value.filter.return_value.all.return_value = [
        SimpleNamespace(
            id="f1", name="Favorito Uno", price=3100, stock=6, is_available=True
        ),
        SimpleNamespace(
            id="f2", name="Favorito Dos", price=4200, stock=2, is_available=True
        ),
    ]
    config = SimpleNamespace(
        favorites_config={
            "enabled": True,
            "title": "Favoritos",
            "mode": "manual",
            "product_ids": ["f1", "f2"],
        }
    )

    with (
        patch("controllers.telegram_controller.SessionLocal", return_value=db_mock),
        patch(
            "controllers.telegram_controller.BusinessConfigService"
        ) as config_service_mock,
    ):
        config_service_mock.return_value.get_config.return_value = config
        from controllers.telegram_controller import _get_favorites_text

        text, _ = _get_favorites_text()

    assert "Favoritos" in text
    assert "Favorito Uno" in text
    assert "Favorito Dos" in text


def test_favorites_text_uses_catalog_cache_without_db_lookup() -> None:
    from controllers import telegram_controller
    from controllers.telegram_controller import _get_favorites_text

    telegram_controller._catalog_snapshot = telegram_controller.CatalogSnapshot(
        products_by_id={
            "f-cache": {
                "id": "f-cache",
                "name": "Favorito Cacheado",
                "price": 4990.0,
                "stock": 2,
                "is_available": True,
            }
        },
        version=1,
    )
    telegram_controller.prime_business_config_cache(
        SimpleNamespace(
            human_agent_available=True,
            promotions_config={},
            best_sellers_config={},
            favorites_config={
                "enabled": True,
                "title": "Favoritos cache",
                "mode": "manual",
                "product_ids": ["f-cache"],
            },
        )
    )

    with patch("controllers.telegram_controller.SessionLocal") as session_mock:
        text, product_names = _get_favorites_text()

    session_mock.assert_not_called()
    assert product_names == ["Favorito Cacheado"]
    assert "Favoritos cache" in text
    assert "Favorito Cacheado" in text


def test_cart_text_still_uses_db_lookup() -> None:
    from controllers.telegram_controller import _get_cart_text

    db_mock = MagicMock()
    user = MagicMock(id=1)
    cart = MagicMock(items=[])
    with (
        patch("controllers.telegram_controller.SessionLocal", return_value=db_mock),
        patch("controllers.telegram_controller.UserService") as user_service_mock,
        patch("controllers.telegram_controller.CartService") as cart_service_mock,
    ):
        user_service_mock.return_value.get_or_create.return_value = user
        cart_service_mock.return_value.get_or_create_cart.return_value = cart

        text = _get_cart_text("user-1")

    user_service_mock.return_value.get_or_create.assert_called_once_with(
        external_id="user-1",
        platform="telegram",
    )
    cart_service_mock.return_value.get_or_create_cart.assert_called_once_with(user.id)
    assert "carrito está vacío" in text


def test_orders_text_still_uses_db_lookup() -> None:
    from controllers.telegram_controller import _get_orders_text

    db_mock = MagicMock()
    user = MagicMock(id=1)
    with (
        patch("controllers.telegram_controller.SessionLocal", return_value=db_mock),
        patch("controllers.telegram_controller.UserService") as user_service_mock,
        patch("controllers.telegram_controller.OrderService") as order_service_mock,
    ):
        user_service_mock.return_value.get_or_create.return_value = user
        order_service_mock.return_value.list_user_orders.return_value = []

        text, has_orders = _get_orders_text("user-1")

    user_service_mock.return_value.get_or_create.assert_called_once_with(
        external_id="user-1",
        platform="telegram",
    )
    order_service_mock.return_value.list_user_orders.assert_called_once_with(user.id)
    assert has_orders is False
    assert "No tienes pedidos" in text
