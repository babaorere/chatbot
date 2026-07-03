from __future__ import annotations

from unittest.mock import MagicMock, patch

from scripts.seed_general_products import (
    GENERAL_PRODUCTS,
    _find_presentation_collisions,
    _reset_existing_general_catalog,
    seed_general,
)


def test_general_products_seed_has_ten_items_and_five_variants() -> None:
    mistral_products = [
        product
        for product in GENERAL_PRODUCTS
        if product.get("presentation_family") == "Pisco Mistral"
    ]

    assert len(GENERAL_PRODUCTS) == 10
    assert len(mistral_products) == 5
    assert {product["format"] for product in mistral_products} == {
        "200cc",
        "350cc",
        "500cc",
        "750cc",
        "1L",
    }


def test_general_products_seed_has_no_equivalent_presentation_collisions() -> None:
    collisions = _find_presentation_collisions(GENERAL_PRODUCTS)

    assert collisions == []


def test_reset_existing_general_catalog_deletes_dependencies_before_products() -> None:
    db_mock = MagicMock()

    _reset_existing_general_catalog(db_mock)

    assert db_mock.execute.call_count == 3


def test_seed_general_recreates_general_catalog_from_scratch() -> None:
    db_mock = MagicMock()
    category_query = MagicMock()
    category_query.filter.return_value.first.return_value = None
    product_query = MagicMock()
    product_query.filter.return_value.first.return_value = None
    db_mock.query.side_effect = [category_query] + [product_query] * len(
        GENERAL_PRODUCTS
    )

    with patch("scripts.seed_general_products.SessionLocal", return_value=db_mock):
        seed_general(reset_existing_products=True)

    assert db_mock.add.call_count == len(GENERAL_PRODUCTS) + 1
    assert db_mock.commit.called
