from __future__ import annotations

from datetime import time
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, RootModel, ValidationError
from pydantic import field_validator, model_validator


FEATURED_PRODUCTS_MAX_ITEMS = 10


class FeaturedProductsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    title: str = Field(default="", max_length=120)
    mode: Literal["manual", "automatic"] = "manual"
    product_ids: list[UUID] = Field(default_factory=list, max_length=FEATURED_PRODUCTS_MAX_ITEMS)

    @field_validator("title", mode="before")
    @classmethod
    def _normalize_title(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @model_validator(mode="after")
    def _validate_products(self) -> FeaturedProductsConfig:
        seen: set[UUID] = set()
        duplicates: list[str] = []
        for product_id in self.product_ids:
            if product_id in seen:
                duplicates.append(str(product_id))
            seen.add(product_id)
        if duplicates:
            raise ValueError("product_ids must not contain duplicates")
        return self

    def to_json_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class DaySchedule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    closed: bool = False
    open: str | None = None
    close: str | None = None

    @model_validator(mode="after")
    def _validate_schedule(self) -> DaySchedule:
        if self.closed:
            return self
        if self.open is None or self.close is None:
            raise ValueError("open days require open and close times")
        open_time = _parse_hhmm(self.open, field_name="open")
        close_time = _parse_hhmm(self.close, field_name="close")
        if close_time <= open_time:
            raise ValueError("close time must be later than open time")
        return self


class BusinessHoursConfig(RootModel[dict[str, DaySchedule]]):
    @model_validator(mode="after")
    def _validate_day_keys(self) -> BusinessHoursConfig:
        for day in self.root:
            if not str(day).strip():
                raise ValueError("business hour day names must not be blank")
        return self

    def to_json_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def default_featured_products_config() -> FeaturedProductsConfig:
    return FeaturedProductsConfig()


def default_featured_products_config_json() -> dict[str, Any]:
    return default_featured_products_config().to_json_dict()


def normalize_featured_products_config(value: Any) -> FeaturedProductsConfig:
    return _validate_as_featured_config(value)


def normalize_featured_products_config_json(value: Any) -> dict[str, Any]:
    return normalize_featured_products_config(value).to_json_dict()


def normalize_business_hours_config(value: Any) -> BusinessHoursConfig:
    if value is None:
        return BusinessHoursConfig.model_validate({})
    return _validate_as_business_hours(value)


def normalize_business_hours_config_json(value: Any) -> dict[str, Any]:
    return normalize_business_hours_config(value).to_json_dict()


def _validate_as_featured_config(value: Any) -> FeaturedProductsConfig:
    try:
        if value is None or value == {}:
            return default_featured_products_config()
        return FeaturedProductsConfig.model_validate(value)
    except ValidationError as exc:
        raise ValueError(f"Invalid featured products config: {exc}") from exc


def _validate_as_business_hours(value: Any) -> BusinessHoursConfig:
    try:
        return BusinessHoursConfig.model_validate(value)
    except ValidationError as exc:
        raise ValueError(f"Invalid business hours config: {exc}") from exc


def _parse_hhmm(value: str, *, field_name: str) -> time:
    try:
        hour_raw, minute_raw = value.split(":", maxsplit=1)
        hour = int(hour_raw)
        minute = int(minute_raw)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must use HH:MM format") from exc
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError(f"{field_name} must use HH:MM format")
    return time(hour=hour, minute=minute)
