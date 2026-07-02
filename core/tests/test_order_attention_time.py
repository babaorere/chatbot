from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from services.order_service import OrderService


def test_update_order_status_sets_confirmed_at_on_confirmation() -> None:
    db_mock = MagicMock()
    order = SimpleNamespace(
        id="order-1",
        status="pending",
        confirmed_at=None,
        items=[],
    )

    service = OrderService(db_mock)
    service.get_order = MagicMock(return_value=order)

    updated = service.update_order_status(order.id, "confirmed")

    assert updated.confirmed_at is not None
    assert updated.status == "confirmed"
    db_mock.flush.assert_called_once()
    db_mock.refresh.assert_called_once_with(order)


def test_get_attention_time_metrics_returns_today_average_minutes() -> None:
    db_mock = MagicMock()
    now = datetime.now()
    orders = [
        SimpleNamespace(
            created_at=now - timedelta(minutes=20),
            confirmed_at=now,
        ),
        SimpleNamespace(
            created_at=now - timedelta(minutes=40),
            confirmed_at=now - timedelta(minutes=10),
        ),
        SimpleNamespace(
            created_at=now - timedelta(days=1, minutes=30),
            confirmed_at=now - timedelta(days=1),
        ),
    ]

    db_mock.query.return_value.filter.return_value.all.return_value = orders
    service = OrderService(db_mock)

    metrics = service.get_attention_time_metrics()

    assert metrics["real_daily_average_minutes"] == 25
    assert metrics["confirmed_orders_count"] == 2
