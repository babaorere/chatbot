from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from controllers.business_config_controller import (
    import_products as admin_import_products,
    update_kb_entry,
    update_product as admin_update_product,
)
from controllers.business_controller import update_product as tenant_update_product
from controllers.category_controller import list_categories
from controllers.order_controller import add_to_cart
from controllers.user_controller import create_user


def test_create_user_hides_internal_error_details() -> None:
    db_mock = MagicMock()
    data = MagicMock(external_id="u1", platform="telegram", display_name="Ana")

    with patch("controllers.user_controller.UserService") as svc_mock:
        svc_instance = MagicMock()
        svc_instance.get_or_create.side_effect = RuntimeError("db exploded")
        svc_mock.return_value = svc_instance

        with pytest.raises(HTTPException) as exc_info:
            create_user(data=data, db=db_mock)

    assert exc_info.value.status_code == 500
    assert "db exploded" not in exc_info.value.detail
    assert exc_info.value.detail == "Failed to create user"


def test_list_categories_hides_internal_error_details() -> None:
    db_mock = MagicMock()

    with patch("controllers.category_controller.CategoryService") as svc_mock:
        svc_instance = MagicMock()
        svc_instance.list_categories.side_effect = RuntimeError("db exploded")
        svc_mock.return_value = svc_instance

        with pytest.raises(HTTPException) as exc_info:
            list_categories(db=db_mock)

    assert exc_info.value.status_code == 500
    assert "db exploded" not in exc_info.value.detail
    assert exc_info.value.detail == "Error al listar categorías"


def test_add_to_cart_hides_internal_error_details() -> None:
    db_mock = MagicMock()
    data = MagicMock(user_id="u1", platform="telegram", product_id="p1", quantity=1)

    with (
        patch("controllers.order_controller.UserService") as user_svc_mock,
        patch("controllers.order_controller.CartService") as cart_svc_mock,
    ):
        user_instance = MagicMock()
        user_instance.get_or_create.side_effect = RuntimeError("db exploded")
        user_svc_mock.return_value = user_instance
        cart_svc_mock.return_value = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            add_to_cart(data=data, db=db_mock)

    assert exc_info.value.status_code == 500
    assert "db exploded" not in exc_info.value.detail
    assert exc_info.value.detail == "Failed to add item to cart"


def test_admin_update_product_maps_missing_product_to_404() -> None:
    db_mock = MagicMock()
    data = MagicMock()

    with patch("controllers.business_config_controller.ProductService") as svc_mock:
        svc_instance = MagicMock()
        svc_instance.update_product.side_effect = ValueError("Product 123 not found")
        svc_mock.return_value = svc_instance

        with pytest.raises(HTTPException) as exc_info:
            admin_update_product(
                product_id="00000000-0000-0000-0000-000000000123",
                data=data,
                db=db_mock,
            )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Product 123 not found"


def test_tenant_update_product_maps_invalid_value_to_400() -> None:
    db_mock = MagicMock()
    data = MagicMock()

    with patch("controllers.business_controller.ProductService") as svc_mock:
        svc_instance = MagicMock()
        svc_instance.update_product.side_effect = ValueError(
            "Precio debe estar entre 0 y 99999999.99"
        )
        svc_mock.return_value = svc_instance

        with pytest.raises(HTTPException) as exc_info:
            tenant_update_product(
                product_id="00000000-0000-0000-0000-000000000123",
                data=data,
                db=db_mock,
            )

    assert exc_info.value.status_code == 400
    assert "Precio debe estar entre" in exc_info.value.detail


def test_admin_import_products_maps_row_validation_error_to_400() -> None:
    db_mock = MagicMock()
    file_mock = MagicMock(filename="productos.xlsx")
    file_mock.file.read.return_value = b"fake-bytes"
    workbook_mock = MagicMock()
    worksheet_mock = MagicMock()
    worksheet_mock.iter_rows.return_value = [("SKU-1", "Producto", None)]
    workbook_mock.active = worksheet_mock

    with (
        patch("controllers.business_config_controller.load_workbook", return_value=workbook_mock),
        patch("controllers.business_config_controller.ProductService") as svc_mock,
    ):
        svc_instance = MagicMock()
        svc_instance.import_from_rows.side_effect = ValueError(
            "Fila 1: Stock debe estar entre 0 y 1000000"
        )
        svc_mock.return_value = svc_instance

        with pytest.raises(HTTPException) as exc_info:
            admin_import_products(file=file_mock, db=db_mock)

    assert exc_info.value.status_code == 400
    assert "Fila 1" in exc_info.value.detail


@pytest.mark.asyncio
async def test_update_kb_entry_maps_missing_entry_to_404() -> None:
    db_mock = MagicMock()
    data = MagicMock(category=None, title=None, content=None, is_active=None)

    with patch("controllers.business_config_controller.KBService") as svc_mock:
        svc_instance = MagicMock()
        svc_instance.update_entry = MagicMock(
            side_effect=ValueError("Knowledge base entry 123 not found")
        )
        svc_mock.return_value = svc_instance

        with pytest.raises(HTTPException) as exc_info:
            await update_kb_entry(
                entry_id="00000000-0000-0000-0000-000000000123",
                data=data,
                db=db_mock,
            )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Knowledge base entry 123 not found"
