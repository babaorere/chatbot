from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from fastapi import APIRouter

from app.container import get_redis_client
from config.settings import settings

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


async def _read_arq_health() -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "enabled": settings.arq_enabled,
        "queue_name": settings.arq_queue_name,
        "worker_status": "disabled" if not settings.arq_enabled else "unknown",
    }
    if not settings.arq_enabled:
        return snapshot

    redis_client = get_redis_client()
    if redis_client is None:
        snapshot["worker_status"] = "redis_unavailable"
        return snapshot

    raw = await redis_client.get(settings.arq_health_check_key)
    if not raw:
        snapshot["worker_status"] = "heartbeat_missing"
        logger.warning(
            "ARQ health check: heartbeat missing [queue=%s key=%s]",
            settings.arq_queue_name,
            settings.arq_health_check_key,
        )
        return snapshot

    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        snapshot["worker_status"] = "heartbeat_corrupt"
        logger.warning(
            "ARQ health check: heartbeat corrupt [queue=%s key=%s]",
            settings.arq_queue_name,
            settings.arq_health_check_key,
        )
        return snapshot

    worker_ts = int(payload.get("timestamp", 0))
    age_seconds = max(0, int(time.time()) - worker_ts)
    snapshot.update(
        {
            "worker_status": "ok" if age_seconds <= 60 else "stale",
            "worker_timestamp": worker_ts,
            "worker_age_seconds": age_seconds,
            "worker_pid": payload.get("pid"),
        }
    )
    if snapshot["worker_status"] == "ok":
        logger.info(
            "ARQ health check: worker ok [queue=%s age_seconds=%s pid=%s]",
            snapshot["queue_name"],
            age_seconds,
            snapshot["worker_pid"],
        )
    else:
        logger.warning(
            "ARQ health check: worker stale [queue=%s age_seconds=%s pid=%s]",
            snapshot["queue_name"],
            age_seconds,
            snapshot["worker_pid"],
        )
    return snapshot


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Expone el estado del proceso FastAPI y la configuración operativa esencial."""
    arq_health = await _read_arq_health()
    return {
        "status": "ok",
        "service": "chatbot-core",
        "version": "1.0.0",
        "single_tenant": "true",
        "session_backend": settings.session_backend,
        "arq": arq_health,
        "worker_pid": str(os.getpid()),
    }
