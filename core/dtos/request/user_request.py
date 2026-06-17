from __future__ import annotations

from pydantic import BaseModel, Field


class UserCreateRequest(BaseModel):
    external_id: str = Field(..., description="External user identifier")
    platform: str = Field(..., description="Platform: telegram, whatsapp, web")
    display_name: str | None = Field(None, description="Human-readable name")
