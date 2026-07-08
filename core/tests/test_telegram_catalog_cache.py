from __future__ import annotations

from unittest.mock import patch

from infrastructure.channels.telegram_menu_flow import TelegramMenuFlow
from infrastructure.channels.telegram_purchase_flow import TelegramPurchaseFlow


def _menu_flow_with_cached_category() -> TelegramMenuFlow:
    return TelegramMenuFlow(
        promotions_builder=lambda: ("", []),
        best_sellers_builder=lambda: ("", []),
        favorites_builder=lambda: ("", []),
        cart_builder=lambda _user_id: ("", False),
        categories_cache=[
            {"name": "Cervezas", "slug": "cervezas", "is_system": False},
        ],
        products_cache={},
    )


def test_purchase_flow_cached_product_quantity_prompt_does_not_query_db() -> None:
    product_id = "4b0f2fc4-274a-46a6-aea1-eed8487a6f20"
    flow = TelegramPurchaseFlow(
        product_cache={
            product_id: {
                "id": product_id,
                "name": "Cerveza Cacheada",
                "price": 2500.0,
                "stock": 12,
                "category": "Cervezas",
                "unit_of_measure": "lata",
            }
        }
    )

    with patch(
        "infrastructure.channels.telegram_purchase_flow.SessionLocal"
    ) as session:
        plan = flow.render_quantity_prompt(product_id=product_id)

    session.assert_not_called()
    assert "Cerveza Cacheada" in plan.text
    assert "lata" in plan.text


def test_menu_flow_cached_category_override_does_not_query_db() -> None:
    flow = _menu_flow_with_cached_category()

    with patch("infrastructure.channels.telegram_menu_flow.SessionLocal") as session:
        scope = flow.try_resolve_category_override("quiero ver cervezas")

    session.assert_not_called()
    assert scope == "category:cervezas"
