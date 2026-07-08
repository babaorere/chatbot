from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from infrastructure.channels.telegram_fsm import TelegramConversationFSM


class TelegramInputKind(str, Enum):
    CALLBACK = "callback"
    COMMAND = "command"
    LEGACY_NUMERIC_MENU = "legacy_numeric_menu"
    TEXT = "text"


@dataclass(frozen=True)
class TelegramInputEvent:
    kind: TelegramInputKind
    text: str | None = None
    callback_data: str | None = None
    callback_query_id: str | None = None
    message_obj: dict[str, Any] | None = None
    callback_query: dict[str, Any] | None = None


class TelegramInputRouter:
    """Normaliza entradas Telegram en eventos canónicos."""

    async def route(
        self,
        *,
        message_obj: dict[str, Any] | None,
        callback_query: dict[str, Any] | None,
        callback_query_id: str | None,
        fsm: TelegramConversationFSM,
    ) -> TelegramInputEvent | None:
        if callback_query is not None:
            callback_data = callback_query.get("data")
            if not callback_data:
                return None
            return TelegramInputEvent(
                kind=TelegramInputKind.CALLBACK,
                callback_data=str(callback_data),
                callback_query_id=callback_query_id,
                callback_query=callback_query,
                message_obj=callback_query.get("message"),
            )

        if message_obj is None:
            return None

        text = message_obj.get("text")
        if not isinstance(text, str) or not text.strip():
            return None

        normalized = text.strip()
        if normalized.startswith("/"):
            return TelegramInputEvent(
                kind=TelegramInputKind.COMMAND,
                text=normalized,
                message_obj=message_obj,
            )

        legacy_callback = await fsm.resolve_legacy_numeric_menu_selection(normalized)
        if legacy_callback is not None:
            current_version = await fsm.get_fsm_version()
            return TelegramInputEvent(
                kind=TelegramInputKind.LEGACY_NUMERIC_MENU,
                text=normalized,
                callback_data=f"{legacy_callback}#{current_version}",
                message_obj=message_obj,
            )

        return TelegramInputEvent(
            kind=TelegramInputKind.TEXT,
            text=normalized,
            message_obj=message_obj,
        )
