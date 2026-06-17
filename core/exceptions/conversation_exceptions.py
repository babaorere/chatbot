from __future__ import annotations


class ConversationNotFoundError(Exception):
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"Conversation not found: {session_id}")
