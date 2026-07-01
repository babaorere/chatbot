from __future__ import annotations

import logging
from typing import Any

from config.database import SessionLocal
from services.alert_service import AlertService

logger = logging.getLogger(__name__)


async def job_notify_critical_issue(
    ctx: dict[str, Any],
    *,
    title: str,
    details: str,
    alert_type: str = "error",
    user_id: str | None = None,
    session_id: str | None = None,
    trace_id: str | None = None,
    event_id: str | None = None,
) -> None:
    """Envía una alerta operativa usando recursos propios del worker."""
    logger.info(
        "ARQ alert job started [job=notify_critical_issue event_id=%s trace_id=%s user_id=%s session_id=%s retry=%s]",
        event_id,
        trace_id,
        user_id,
        session_id,
        ctx.get("job_try"),
    )
    db = SessionLocal()
    try:
        await AlertService.notify_critical_issue(
            db=db,
            title=title,
            details=details,
            alert_type=alert_type,
        )
    finally:
        db.close()


async def job_check_llm_latency(
    ctx: dict[str, Any],
    *,
    duration: float,
    user_id: str,
    session_id: str,
    trace_id: str | None = None,
    event_id: str | None = None,
) -> None:
    """Evalúa latencia del LLM usando recursos propios del worker."""
    logger.info(
        "ARQ alert job started [job=check_llm_latency event_id=%s trace_id=%s user_id=%s session_id=%s retry=%s duration=%.2f]",
        event_id,
        trace_id,
        user_id,
        session_id,
        ctx.get("job_try"),
        duration,
    )
    db = SessionLocal()
    try:
        await AlertService.check_llm_latency(
            db=db,
            duration=duration,
            user_id=user_id,
            session_id=session_id,
        )
    finally:
        db.close()
