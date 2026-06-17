from __future__ import annotations

from pydantic import BaseModel


class ChatResponse(BaseModel):
    session_id: str
    user_id: str
    tenant_slug: str
    response: str


class SessionHistoryItem(BaseModel):
    author: str
    content: str
