from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

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

    with patch("controllers.order_controller.UserService") as user_svc_mock, patch(
        "controllers.order_controller.CartService"
    ) as cart_svc_mock:
        user_instance = MagicMock()
        user_instance.get_or_create.side_effect = RuntimeError("db exploded")
        user_svc_mock.return_value = user_instance
        cart_svc_mock.return_value = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            add_to_cart(data=data, db=db_mock)

    assert exc_info.value.status_code == 500
    assert "db exploded" not in exc_info.value.detail
    assert exc_info.value.detail == "Failed to add item to cart"
