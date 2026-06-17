from __future__ import annotations

from pydantic import BaseModel


class ConversationResponse(BaseModel):
    id: int
    user_id: int
    session_id: str

    model_config = {"from_attributes": True}
