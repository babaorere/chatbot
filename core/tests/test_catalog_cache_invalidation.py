from __future__ import annotations

from unittest.mock import MagicMock, patch

from controllers import (
    business_config_controller,
    business_controller,
    category_controller,
)


def _product_data() -> MagicMock:
    return MagicMock(
        sku="SKU-1",
        name="Producto",
        description=None,
        price=1000.0,
        stock=5,
        category="General",
        is_available=True,
        cost=None,
        margin=None,
        provider=None,
        taxes=0.19,
        unit_of_measure="un",
        format=None,
    )


def test_business_config_create_product_refreshes_catalog_cache_after_commit() -> None:
    db = MagicMock()
    product = MagicMock()

    with (
        patch("controllers.business_config_controller.ProductService") as service_mock,
        patch(
            "controllers.business_config_controller.ProductResponse.model_validate",
            return_value="response",
        ),
        patch(
            "controllers.business_config_controller.refresh_catalog_cache_after_commit"
        ) as refresh_mock,
    ):
        service_mock.return_value.create_product.return_value = product

        result = business_config_controller.create_product(data=_product_data(), db=db)

    assert result == "response"
    refresh_mock.assert_called_once_with("business_config_product_created")


def test_business_me_import_products_refreshes_catalog_cache_after_transaction() -> (
    None
):
    db = MagicMock()
    file = MagicMock()
    file.file.read.return_value = b"xlsx-bytes"
    row_values = [None for _ in business_controller.FIELD_NAMES]
    row_values[business_controller.FIELD_NAMES.index("name")] = "Producto importado"

    workbook = MagicMock()
    workbook.active.iter_rows.return_value = [tuple(row_values)]

    with (
        patch("controllers.business_controller.load_workbook", return_value=workbook),
        patch("controllers.business_controller.ProductService") as service_mock,
        patch(
            "controllers.business_controller.refresh_catalog_cache_after_commit"
        ) as refresh_mock,
    ):
        service_mock.return_value.import_from_rows.return_value = {
            "created": 1,
            "updated": 0,
            "errors": 0,
        }

        result = business_controller.import_products(file=file, db=db)

    assert result["status"] == "ok"
    assert result["rows_processed"] == 1
    db.begin.assert_called_once()
    refresh_mock.assert_called_once_with("business_me_products_imported")


def test_create_category_refreshes_catalog_cache_after_commit() -> None:
    db = MagicMock()
    category = MagicMock()
    category.to_dict.return_value = {"name": "Cervezas", "slug": "cervezas"}

    with (
        patch("controllers.category_controller.CategoryService") as service_mock,
        patch(
            "controllers.category_controller.refresh_catalog_cache_after_commit"
        ) as refresh_mock,
    ):
        service_mock.return_value.create_category.return_value = category

        result = category_controller.create_category(
            data=category_controller.CategoryCreateRequest(name="Cervezas"),
            db=db,
        )

    assert result["status"] == "success"
    refresh_mock.assert_called_once_with("category_created")
