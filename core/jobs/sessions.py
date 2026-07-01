from __future__ import annotations

import logging
from typing import Any

from services.conversation_reset_service import clear_latest_conversation_session

logger = logging.getLogger(__name__)


async def job_clear_latest_conversation_session(
    ctx: dict[str, Any],
    *,
    user_id: str,
    trace_id: str | None = None,
    reason: str | None = None,
    event_id: str | None = None,
) -> None:
    """Limpia de forma durable la última sesión conversacional de un usuario."""
    logger.info(
        "ARQ session reset job started [job=clear_latest_conversation_session event_id=%s trace_id=%s user_id=%s retry=%s reason=%s]",
        event_id,
        trace_id,
        user_id,
        ctx.get("job_try"),
        reason,
    )
    session_id = await clear_latest_conversation_session(user_id)
    logger.info(
        "ARQ session reset job completed [event_id=%s trace_id=%s user_id=%s session_id=%s]",
        event_id,
        trace_id,
        user_id,
        session_id or "-",
    )
