from __future__ import annotations

from unittest.mock import patch

from infrastructure.channels.telegram_menu_flow import TelegramMenuFlow
from infrastructure.channels.telegram_purchase_flow import TelegramPurchaseFlow
from infrastructure.channels.telegram_menu_flow import (
    CART_MENU_SCOPE,
    CATEGORIES_MENU_SCOPE,
    CATEGORY_SCOPE_PREFIX,
)


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


def test_static_menu_prerender_is_versioned_by_catalog_snapshot() -> None:
    from controllers import telegram_controller

    telegram_controller._catalog_snapshot = telegram_controller.CatalogSnapshot(
        categories=({"name": "Cervezas", "slug": "cervezas", "is_system": False},),
        products_by_category={
            "Cervezas": (
                {
                    "id": "p1",
                    "name": "Cerveza Cacheada",
                    "price": 2500.0,
                    "stock": 12,
                    "category": "Cervezas",
                    "is_available": True,
                    "unit_of_measure": "lata",
                },
            )
        },
        products_by_id={},
        version=1,
    )
    telegram_controller._categories_cache = list(
        telegram_controller._catalog_snapshot.categories
    )
    telegram_controller._products_by_category_cache = {
        category: list(products)
        for category, products in telegram_controller._catalog_snapshot.products_by_category.items()
    }
    telegram_controller._static_menu_prerender_snapshot = (
        telegram_controller.StaticMenuPrerenderSnapshot()
    )

    first = telegram_controller._get_static_menu_prerenders()

    telegram_controller._catalog_snapshot = telegram_controller.CatalogSnapshot(
        categories=({"name": "Vinos", "slug": "vinos", "is_system": False},),
        products_by_category={},
        products_by_id={},
        version=2,
    )
    telegram_controller._categories_cache = list(
        telegram_controller._catalog_snapshot.categories
    )
    telegram_controller._products_by_category_cache = {
        category: list(products)
        for category, products in telegram_controller._catalog_snapshot.products_by_category.items()
    }
    second = telegram_controller._get_static_menu_prerenders()

    assert first.catalog_version == 1
    assert second.catalog_version == 2
    assert f"{CATEGORY_SCOPE_PREFIX}cervezas" in first.plans_by_scope
    assert f"{CATEGORY_SCOPE_PREFIX}vinos" in second.plans_by_scope
    assert f"{CATEGORY_SCOPE_PREFIX}cervezas" not in second.plans_by_scope


def test_static_menu_prerender_excludes_user_scoped_cart() -> None:
    from controllers import telegram_controller

    telegram_controller._catalog_snapshot = telegram_controller.CatalogSnapshot(
        categories=(),
        products_by_category={},
        products_by_id={},
        version=10,
    )
    telegram_controller._categories_cache = []
    telegram_controller._products_by_category_cache = {}
    telegram_controller._static_menu_prerender_snapshot = (
        telegram_controller.StaticMenuPrerenderSnapshot()
    )

    snapshot = telegram_controller._get_static_menu_prerenders()

    assert CART_MENU_SCOPE not in snapshot.plans_by_scope


def test_static_menu_prerender_keeps_unversioned_callback_data() -> None:
    from controllers import telegram_controller

    telegram_controller._catalog_snapshot = telegram_controller.CatalogSnapshot(
        categories=({"name": "Cervezas", "slug": "cervezas", "is_system": False},),
        products_by_category={},
        products_by_id={},
        version=11,
    )
    telegram_controller._categories_cache = list(
        telegram_controller._catalog_snapshot.categories
    )
    telegram_controller._products_by_category_cache = {}
    telegram_controller._static_menu_prerender_snapshot = (
        telegram_controller.StaticMenuPrerenderSnapshot()
    )

    plan = telegram_controller._render_static_menu_plan(
        CATEGORIES_MENU_SCOPE,
        current_stack=["menu:main"],
    )

    assert plan is not None
    callback_values = [
        button["callback_data"]
        for row in plan.reply_markup["inline_keyboard"]
        for button in row
        if "callback_data" in button
    ]
    assert "cat_select:cervezas" in callback_values
    assert all("#" not in callback_data for callback_data in callback_values)
