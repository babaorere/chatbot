from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch


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

        text = _get_promotions_text()

    assert "Promociones de hoy" in text
    assert "Promo Uno" in text
    assert "Promo Dos" in text


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

        text = _get_best_sellers_text()

    assert "Más vendidos" in text
    assert "Más Uno" in text
    assert "Más Dos" in text


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

        text = _get_favorites_text()

    assert "Favoritos" in text
    assert "Favorito Uno" in text
    assert "Favorito Dos" in text
