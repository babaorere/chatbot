from __future__ import annotations

from contextlib import nullcontext
from unittest.mock import MagicMock, patch

from controllers.order_controller import checkout


def test_checkout_returns_customer_message_with_estimated_minutes() -> None:
    db_mock = MagicMock()
    user_mock = MagicMock(id=42)
    order_mock = MagicMock()
    order_mock.to_dict.return_value = {
        "id": "order-123",
        "total_amount": 20480.0,
    }

    with patch("controllers.order_controller.UserService") as user_svc_mock, patch(
        "controllers.order_controller.OrderService"
    ) as order_svc_mock, patch(
        "controllers.order_controller.BusinessConfigService"
    ) as config_svc_mock, patch(
        "controllers.order_controller.safe_transaction",
        return_value=nullcontext(),
    ):
        user_instance = MagicMock()
        user_instance.get_or_create.return_value = user_mock
        user_svc_mock.return_value = user_instance

        order_instance = MagicMock()
        order_instance.checkout_cart.return_value = order_mock
        order_svc_mock.return_value = order_instance

        config_instance = MagicMock()
        config_instance.get_config.return_value = MagicMock(
            estimated_attention_minutes=35
        )
        config_svc_mock.return_value = config_instance

        result = checkout(
            data=MagicMock(
                user_id="u1",
                platform="telegram",
                session_id="session-1",
                delivery_address="Av. Principal 123",
                payment_method="transfer",
            ),
            db=db_mock,
        )

    assert result["estimated_attention_minutes"] == 35
    assert "Tiempo estimado de atención: 35 minutos." in result["customer_message"]
    assert "order-123" in result["customer_message"]
