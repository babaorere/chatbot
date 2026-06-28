from __future__ import annotations

import uuid
from pydantic import BaseModel


class BusinessConfigResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: str | None
    phone: str | None
    address: str | None
    city: str | None
    website: str | None
    logo_url: str | None
    business_hours: dict | None

    model_config = {"from_attributes": True}


class ProductResponse(BaseModel):
    id: uuid.UUID
    sku: str | None
    name: str
    description: str | None
    price: float | None
    stock: int
    category: str | None
    is_available: bool
    cost: float | None
    margin: float | None
    provider: str | None
    taxes: float | None
    unit_of_measure: str | None
    format: str | None

    model_config = {"from_attributes": True}


class KBEntryResponse(BaseModel):
    id: uuid.UUID
    category: str
    title: str
    content: str
    is_active: bool

    model_config = {"from_attributes": True}


class KBSearchResultItem(BaseModel):
    id: uuid.UUID
    category: str
    title: str
    content: str
    rank: float


class KBSearchResponse(BaseModel):
    query: str
    results: list[KBSearchResultItem]
    count: int


class CategoryCountResponse(BaseModel):
    category: str
    count: int
