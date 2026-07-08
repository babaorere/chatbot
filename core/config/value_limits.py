from __future__ import annotations

import math
from typing import TypeVar

TFloat = TypeVar("TFloat", int, float)

CART_QUANTITY_MIN = 1
CART_QUANTITY_MAX = 1000

PRODUCT_STOCK_MIN = 0
PRODUCT_STOCK_MAX = 1_000_000

PRODUCT_MONEY_MIN = 0.0
PRODUCT_MONEY_MAX = 99_999_999.99

PRODUCT_TAX_MIN = 0.0
PRODUCT_TAX_MAX = 1.0

PRODUCT_MARGIN_MIN = 0.0
PRODUCT_MARGIN_MAX = 1000.0

PAGINATION_SKIP_MIN = 0
PAGINATION_SKIP_MAX = 10_000
PAGINATION_LIMIT_MIN = 1
PAGINATION_LIMIT_MAX = 100


def ensure_int_range(
    value: int,
    *,
    name: str,
    min_value: int,
    max_value: int,
) -> int:
    if value < min_value or value > max_value:
        raise ValueError(f"{name} debe estar entre {min_value} y {max_value}")
    return value


def ensure_optional_float_range(
    value: TFloat | None,
    *,
    name: str,
    min_value: float,
    max_value: float,
) -> TFloat | None:
    if value is None:
        return None
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < min_value or parsed > max_value:
        raise ValueError(f"{name} debe estar entre {min_value:g} y {max_value:g}")
    return value
