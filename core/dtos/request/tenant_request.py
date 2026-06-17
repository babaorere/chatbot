from __future__ import annotations

from pydantic import BaseModel, Field


class TenantCreateRequest(BaseModel):
    slug: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    instruction: str | None = None
    model: str | None = None
    api_key: str | None = None
    portal_token: str | None = None


class ChannelRouteCreateRequest(BaseModel):
    platform: str = Field(..., min_length=1, max_length=20)
    channel_identifier: str = Field(..., min_length=1, max_length=255)


class TenantProfileUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=50)
    address: str | None = None
    city: str | None = Field(None, max_length=100)
    website: str | None = Field(None, max_length=255)
    logo_url: str | None = Field(None, max_length=500)
    business_hours: dict | None = None


class ProductCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    price: float | None = Field(None, ge=0)
    stock: int = Field(default=0, ge=0)
    category: str | None = Field(None, max_length=100)
    is_available: bool = True


class ProductUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    price: float | None = Field(None, ge=0)
    stock: int | None = Field(None, ge=0)
    category: str | None = Field(None, max_length=100)
    is_available: bool | None = None


class KBEntryCreateRequest(BaseModel):
    category: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)


class KBEntryUpdateRequest(BaseModel):
    category: str | None = Field(None, min_length=1, max_length=100)
    title: str | None = Field(None, min_length=1)
    content: str | None = Field(None, min_length=1)
    is_active: bool | None = None


class KBSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)
    category: str | None = None
