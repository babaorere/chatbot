from __future__ import annotations

import logging
from typing import Any

from services.telegram_service import clear_telegram_reply_markup

logger = logging.getLogger(__name__)


async def job_clear_reply_markup(
    ctx: dict[str, Any],
    *,
    token: str,
    chat_id: str | int,
    message_id: int,
    trace_id: str | None = None,
    user_id: str | None = None,
    event_id: str | None = None,
) -> None:
    """Limpia de forma durable el teclado inline de un mensaje de Telegram."""
    logger.info(
        "ARQ telegram job started [job=clear_reply_markup event_id=%s trace_id=%s user_id=%s message_id=%s retry=%s]",
        event_id,
        trace_id,
        user_id,
        message_id,
        ctx.get("job_try"),
    )
    try:
        await clear_telegram_reply_markup(
            bot_token=token,
            chat_id=chat_id,
            message_id=message_id,
            trace_id=trace_id,
        )
    except Exception:
        logger.exception(
            "ARQ telegram job failed [job=clear_reply_markup event_id=%s trace_id=%s user_id=%s message_id=%s retry=%s]",
            event_id,
            trace_id,
            user_id,
            message_id,
            ctx.get("job_try"),
        )
        raise
    logger.info(
        "ARQ telegram job completed [job=clear_reply_markup event_id=%s trace_id=%s user_id=%s message_id=%s]",
        event_id,
        trace_id,
        user_id,
        message_id,
    )
