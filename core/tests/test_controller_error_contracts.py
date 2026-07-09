from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from controllers.business_config_controller import (
    import_products as admin_import_products,
    update_profile as admin_update_profile,
    update_kb_entry,
    update_product as admin_update_product,
)
from controllers.business_controller import (
    update_product as tenant_update_product,
    update_profile as tenant_update_profile,
)
from controllers.category_controller import list_categories
from controllers.order_controller import add_to_cart, cancel_order, update_order_status
from controllers.chat_controller import chat
from controllers.session_controller import get_session_history, list_conversations
from controllers.user_controller import create_user
from dtos.request import ChatRequest


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

    with (
        patch("controllers.business_config_controller.ProductService") as svc_mock,
    ):
        svc_instance = MagicMock()
        svc_instance.import_from_workbook_bytes.side_effect = ValueError(
            "Fila 1: Stock debe estar entre 0 y 1000000"
        )
        svc_mock.return_value = svc_instance

        with pytest.raises(HTTPException) as exc_info:
            admin_import_products(file=file_mock, db=db_mock)

    assert exc_info.value.status_code == 400
    assert "Fila 1" in exc_info.value.detail


def test_admin_update_profile_maps_invalid_config_to_400() -> None:
    db_mock = MagicMock()
    data = MagicMock(
        name=None,
        email=None,
        phone=None,
        address=None,
        city=None,
        website=None,
        logo_url=None,
        business_hours={"Lunes": {"open": "25:00", "close": "26:00"}},
        promotions_config=None,
        best_sellers_config=None,
        favorites_config=None,
        estimated_attention_minutes=None,
        human_agent_available=None,
    )

    with patch("controllers.business_config_controller.BusinessConfigService") as svc_mock:
        svc_mock.return_value.update_config.side_effect = ValueError(
            "Invalid business hours config"
        )

        with pytest.raises(HTTPException) as exc_info:
            admin_update_profile(data=data, db=db_mock)

    assert exc_info.value.status_code == 400
    assert "Invalid business hours config" in exc_info.value.detail


def test_tenant_update_profile_primes_full_business_config_cache() -> None:
    db_mock = MagicMock()
    config_mock = MagicMock(human_agent_available=True)
    data = MagicMock(
        name=None,
        email=None,
        phone=None,
        address=None,
        city=None,
        website=None,
        logo_url=None,
        business_hours=None,
        promotions_config=None,
        best_sellers_config=None,
        favorites_config=None,
        estimated_attention_minutes=None,
        human_agent_available=True,
    )

    with (
        patch("controllers.business_controller.BusinessConfigService") as svc_mock,
        patch("controllers.business_controller.prime_business_config_cache") as prime_mock,
        patch("controllers.business_controller.prime_human_agent_cache"),
        patch(
            "controllers.business_controller.BusinessConfigResponse.model_validate",
            return_value={"ok": True},
        ),
    ):
        svc_mock.return_value.update_config.return_value = config_mock

        result = tenant_update_profile(data=data, db=db_mock)

    assert result == {"ok": True}
    prime_mock.assert_called_once_with(config=config_mock)


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


def test_update_order_status_maps_missing_order_to_404() -> None:
    db_mock = MagicMock()
    data = MagicMock(status="confirmed")

    with patch("controllers.order_controller.OrderService") as svc_mock:
        svc_instance = MagicMock()
        svc_instance.update_order_status.side_effect = ValueError("Order not found")
        svc_mock.return_value = svc_instance

        with pytest.raises(HTTPException) as exc_info:
            update_order_status(
                order_id="00000000-0000-0000-0000-000000000123",
                data=data,
                db=db_mock,
                admin_key="admin",
            )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Order not found"


def test_cancel_order_maps_unauthorized_to_403() -> None:
    db_mock = MagicMock()
    data = MagicMock(user_id="u1", platform="telegram")

    with (
        patch("controllers.order_controller.UserService") as user_svc_mock,
        patch("controllers.order_controller.OrderService") as order_svc_mock,
        patch("controllers.order_controller.safe_transaction") as tx_mock,
    ):
        user_instance = MagicMock()
        user_instance.get_or_create.return_value = MagicMock(id=99)
        user_svc_mock.return_value = user_instance

        order_instance = MagicMock()
        order_instance.cancel_order.side_effect = ValueError(
            "No autorizado para cancelar este pedido"
        )
        order_svc_mock.return_value = order_instance
        tx_mock.return_value.__enter__.return_value = None
        tx_mock.return_value.__exit__.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            cancel_order(
                order_id="00000000-0000-0000-0000-000000000123",
                data=data,
                db=db_mock,
            )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "No autorizado para cancelar este pedido"


@pytest.mark.asyncio
async def test_chat_hides_internal_error_details_in_http_500() -> None:
    uc_mock = AsyncMock()
    uc_mock.execute.side_effect = RuntimeError("llm backend exploded")
    request_dto = ChatRequest(
        user_id="123",
        platform="web",
        message="hola",
        session_id="preview-123",
    )

    with pytest.raises(HTTPException) as exc_info:
        await chat(
            request=request_dto,
            process_message_uc=uc_mock,
            fastapi_request=None,
            token_data={"sub": "123"},
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to process chat message"


@pytest.mark.asyncio
async def test_get_session_history_hides_internal_error_details() -> None:
    llm_mock = AsyncMock()
    llm_mock.get_session_history.side_effect = RuntimeError("history backend exploded")

    with pytest.raises(HTTPException) as exc_info:
        await get_session_history(
            session_id="s1",
            user_id="u1",
            db=MagicMock(),
            llm=llm_mock,
            fastapi_request=None,
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to retrieve session history"


def test_list_conversations_hides_internal_error_details() -> None:
    db_mock = MagicMock()
    db_mock.execute.side_effect = RuntimeError("rls exploded")

    with pytest.raises(HTTPException) as exc_info:
        list_conversations(user_id=1, db=db_mock, fastapi_request=None)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to list conversations"
