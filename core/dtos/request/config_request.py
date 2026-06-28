from __future__ import annotations

from pydantic import BaseModel, Field


class BusinessConfigUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=50)
    address: str | None = None
    city: str | None = Field(None, max_length=100)
    website: str | None = Field(None, max_length=255)
    logo_url: str | None = Field(None, max_length=500)
    business_hours: dict | None = None


class ProductCreateRequest(BaseModel):
    sku: str | None = Field(None, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    price: float | None = Field(None, ge=0)
    stock: int = Field(default=0, ge=0)
    category: str | None = Field(None, max_length=100)
    is_available: bool = True
    cost: float | None = Field(None, ge=0)
    margin: float | None = Field(None, ge=0)
    provider: str | None = Field(None, max_length=100)
    taxes: float | None = Field(0.19, ge=0, le=1)
    unit_of_measure: str | None = Field("un", max_length=20)
    format: str | None = Field(None, max_length=100)


class ProductUpdateRequest(BaseModel):
    sku: str | None = Field(None, max_length=50)
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    price: float | None = Field(None, ge=0)
    stock: int | None = Field(None, ge=0)
    category: str | None = Field(None, max_length=100)
    is_available: bool | None = None
    cost: float | None = Field(None, ge=0)
    margin: float | None = Field(None, ge=0)
    provider: str | None = Field(None, max_length=100)
    taxes: float | None = Field(None, ge=0, le=1)
    unit_of_measure: str | None = Field(None, max_length=20)
    format: str | None = Field(None, max_length=100)


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
