from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    user_id: str = Field(..., description="External user ID (e.g., telegram_id)")
    platform: str = Field(..., description="Platform: telegram, whatsapp, web")
    message: str = Field(..., min_length=1, description="User message")
    session_id: str | None = Field(
        None, description="Session ID (auto-generated if None)"
    )
