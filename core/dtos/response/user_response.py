from __future__ import annotations

from pydantic import BaseModel


class UserResponse(BaseModel):
    id: int
    external_id: str
    platform: str
    display_name: str | None

    model_config = {"from_attributes": True}
