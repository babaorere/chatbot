from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from domain.business_config import (
    BusinessHoursConfig,
    FeaturedProductsConfig,
    default_featured_products_config_json,
    normalize_business_hours_config_json,
    normalize_featured_products_config,
    normalize_featured_products_config_json,
)
from services import business_config_cache_service
from services.business_config_service import BusinessConfigService


PRODUCT_ONE_ID = "00000000-0000-0000-0000-000000000401"
PRODUCT_TWO_ID = "00000000-0000-0000-0000-000000000402"


def test_featured_config_empty_dict_normalizes_to_default_json() -> None:
    assert normalize_featured_products_config_json({}) == {
        "enabled": False,
        "title": "",
        "mode": "manual",
        "product_ids": [],
    }


def test_featured_config_valid_manual_selection_preserves_order() -> None:
    result = normalize_featured_products_config_json(
        {
            "enabled": True,
            "title": " Selección ",
            "mode": "manual",
            "product_ids": [PRODUCT_ONE_ID, PRODUCT_TWO_ID],
        }
    )

    assert result == {
        "enabled": True,
        "title": "Selección",
        "mode": "manual",
        "product_ids": [PRODUCT_ONE_ID, PRODUCT_TWO_ID],
    }


@pytest.mark.parametrize(
    "payload, match",
    [
        (
            {
                "enabled": True,
                "title": "Promo",
                "mode": "manual",
                "product_ids": ["not-a-uuid"],
            },
            "Invalid featured products config",
        ),
        (
            {
                "enabled": True,
                "title": "Promo",
                "mode": "manual",
                "product_ids": [PRODUCT_ONE_ID, PRODUCT_ONE_ID],
            },
            "duplicates",
        ),
        (
            {
                "enabled": True,
                "title": "Promo",
                "mode": "manual",
                "product_ids": [],
                "unexpected": True,
            },
            "Extra inputs are not permitted",
        ),
    ],
)
def test_featured_config_invalid_shapes_raise_value_error(
    payload: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        normalize_featured_products_config(payload)


def test_business_hours_accepts_frontend_closed_day_shape() -> None:
    result = normalize_business_hours_config_json(
        {
            "Lunes": {"open": "10:00", "close": "22:00"},
            "Domingo": {"closed": True, "open": None, "close": None},
            "lunes": {"open": "09:00", "close": "18:00"},
        }
    )

    assert result["Domingo"] == {"closed": True, "open": None, "close": None}
    assert result["lunes"]["open"] == "09:00"


@pytest.mark.parametrize(
    "payload, match",
    [
        ({"Lunes": {"open": "10:00"}}, "open days require open and close times"),
        (
            {"Lunes": {"open": "22:00", "close": "10:00"}},
            "close time must be later",
        ),
        ({"Lunes": {"open": "10:99", "close": "12:00"}}, "HH:MM"),
        ({"Lunes": "10:00-12:00"}, "Input should be a valid dictionary"),
        ({"": {"open": "10:00", "close": "12:00"}}, "must not be blank"),
    ],
)
def test_business_hours_invalid_shapes_raise_value_error(
    payload: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        normalize_business_hours_config_json(payload)


def test_business_config_service_normalizes_config_before_persistence() -> None:
    db_mock = MagicMock()
    config = SimpleNamespace(
        name="Demo",
        email=None,
        phone=None,
        address=None,
        city=None,
        website=None,
        logo_url=None,
        business_hours={},
        promotions_config={},
        best_sellers_config={},
        favorites_config={},
        estimated_attention_minutes=30,
        human_agent_available=True,
    )

    with patch("services.business_config_service.BusinessConfigRepository") as repo_mock:
        repo_mock.return_value.get_config.return_value = config
        service = BusinessConfigService(db_mock)

        result = service.update_config(
            business_hours={"Lunes": {"open": "10:00", "close": "22:00"}},
            promotions_config={
                "enabled": True,
                "title": "Promo",
                "mode": "manual",
                "product_ids": [PRODUCT_ONE_ID],
            },
        )

    assert result.business_hours == {
        "Lunes": {"closed": False, "open": "10:00", "close": "22:00"}
    }
    assert result.promotions_config["product_ids"] == [PRODUCT_ONE_ID]
    db_mock.flush.assert_called_once()
    db_mock.refresh.assert_called_once_with(config)


def test_business_config_cache_rejects_corrupt_persisted_config_without_replacing_snapshot() -> None:
    previous = business_config_cache_service.prime_business_config_cache(
        config=SimpleNamespace(
            human_agent_available=True,
            business_hours={},
            promotions_config=default_featured_products_config_json(),
            best_sellers_config=default_featured_products_config_json(),
            favorites_config=default_featured_products_config_json(),
        )
    )

    with pytest.raises(RuntimeError, match="Failed to prime business config cache"):
        business_config_cache_service.prime_business_config_cache(
            config=SimpleNamespace(
                human_agent_available=False,
                business_hours={"Lunes": "10:00-12:00"},
                promotions_config={"enabled": True, "unexpected": True},
                best_sellers_config={},
                favorites_config={},
            )
        )

    assert business_config_cache_service._business_config_snapshot is previous


def test_response_models_keep_typed_config_instances() -> None:
    featured = FeaturedProductsConfig.model_validate(
        {
            "enabled": True,
            "title": "Promo",
            "mode": "manual",
            "product_ids": [PRODUCT_ONE_ID],
        }
    )
    hours = BusinessHoursConfig.model_validate(
        {"Lunes": {"open": "10:00", "close": "22:00"}}
    )

    assert featured.to_json_dict()["product_ids"] == [PRODUCT_ONE_ID]
    assert hours.to_json_dict()["Lunes"]["close"] == "22:00"
