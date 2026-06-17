from __future__ import annotations

import uuid
from pydantic import BaseModel


class TenantResponse(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    status: str

    model_config = {"from_attributes": True}


class ChannelRouteResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    platform: str
    channel_identifier: str

    model_config = {"from_attributes": True}


class TenantProfileResponse(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    email: str | None
    phone: str | None
    address: str | None
    city: str | None
    website: str | None
    logo_url: str | None
    business_hours: dict | None
    status: str

    model_config = {"from_attributes": True}


class ProductResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    price: float | None
    stock: int
    category: str | None
    is_available: bool

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
